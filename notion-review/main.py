# -*- coding: utf-8 -*-
"""
Notion 智能任务与复盘系统 v8 (Final)
功能概览:
 - 每日 00:00: 自动顺延未完成任务 -> 把来源日期改为今日
 - 每日 23:55: 创建/更新每日复盘子页面（保留手动填写内容）
 - 每周（周日 23:55）: 自动生成每周复盘（从每日复盘汇总）
 - 每月（当月最后一天 23:55）: 自动生成每月复盘
 - 启动时自动检测并补齐数据库字段
 - system_check() 每次运行前做健康检查
 - config.json 管理配置，不把 token 硬编码在脚本中
"""

import os
import sys
import json
import traceback
import requests
import subprocess
from datetime import datetime, timedelta
from collections import Counter
import pytz

# ---------------- auto-install minimal package ----------------
def ensure_pkg(pkg):
    try:
        __import__(pkg)
    except ImportError:
        print(f"⚙️ 未检测到模块 {pkg}，自动安装中...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

ensure_pkg("schedule")
import schedule
# ----------------------------------------------------------------

# ---------------- load config.json ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError("❌ 未找到 config.json，请参考 README 创建并填写 NOTION_TOKEN 与数据库 ID。")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)

NOTION_TOKEN = cfg.get("NOTION_TOKEN")
TASK_DB_ID = cfg.get("TASK_DATABASE_ID")             # 任务数据库
DAILY_REVIEW_DB_ID = cfg.get("REVIEW_DAILY_DB_ID")  # 每日复盘数据库（子页面库）
CYCLE_REVIEW_DB_ID = cfg.get("REVIEW_CYCLE_DB_ID")  # 周/月复盘数据库（可与 DAILY 同库，也可分开）
OPENAI_API_KEY = cfg.get("OPENAI_API_KEY")          # 可选，若启用 AI 总结
OPENAI_MODEL = cfg.get("OPENAI_MODEL", "gpt-4o-mini")

if not NOTION_TOKEN or not TASK_DB_ID:
    raise SystemExit("请在 config.json 中设置 NOTION_TOKEN 与 TASK_DATABASE_ID 并重启脚本。")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

tz = pytz.timezone(cfg.get("TZ", "Asia/Shanghai"))
now = datetime.now(tz)
TODAY = now.strftime("%Y-%m-%d")

# ---------------- logging util ----------------
def log(msg):
    print(f"[{datetime.now(tz).isoformat()}] {msg}")

# ---------------- Notion helpers ----------------
def notion_get(url):
    r = requests.get(url, headers=HEADERS)
    return r

def notion_post(url, payload):
    r = requests.post(url, headers=HEADERS, json=payload)
    return r

def notion_patch(url, payload):
    r = requests.patch(url, headers=HEADERS, json=payload)
    return r

# ---------------- DB schema helpers ----------------
def get_database_info(dbid):
    r = notion_get(f"https://api.notion.com/v1/databases/{dbid}")
    if r.status_code != 200:
        log(f"ERROR: get_database_info {dbid} -> {r.status_code} {r.text}")
        return None
    return r.json()

def ensure_props_on_db(dbid, required_props):
    """
    required_props: dict: { "字段名": property_schema }
    property_schema is in Notion API format, e.g. {"number":{}} or {"title":{}}
    """
    info = get_database_info(dbid)
    if not info:
        return False
    existing = set(info.get("properties", {}).keys())
    to_add = {k:v for k,v in required_props.items() if k not in existing}
    if not to_add:
        log(f"✅ 数据库 {dbid} 已包含所有必要字段。")
        return True
    payload = {"properties": to_add}
    r = notion_patch(f"https://api.notion.com/v1/databases/{dbid}", payload)
    if r.status_code in (200,201):
        log(f"⚙️ 已自动补齐数据库 {dbid} 字段：{', '.join(to_add.keys())}")
        return True
    else:
        log(f"❌ 补齐数据库字段失败：{r.status_code} {r.text}")
        return False

# ---------------- match task DB column names (容错匹配) ----------------
def match_task_columns(dbinfo):
    props = dbinfo.get("properties", {})
    cols = {}
    for name, meta in props.items():
        t = meta.get("type")
        lname = name.lower()
        if t == "title" and "title" not in cols:
            cols["title"] = name
        if t == "date" and ("来源" in name or "来源" in lname or "date" in lname or "日" in name):
            cols["source_date"] = name
        if t == "date" and "date" not in cols:
            cols["date"] = name
        if t == "select" and ("状" in name or "状态" in name or "status" in lname):
            cols["status"] = name
        if t == "url" and "resource" not in cols:
            cols["resource"] = name
        if t == "number" and ("时" in name or "时长" in name or "duration" in lname):
            cols["duration"] = name
        if t == "rich_text" and ("提" in name or "提示" in name or "hint" in lname):
            cols["hint"] = name
    # fallback
    for name, meta in props.items():
        if meta.get("type") == "title" and "title" not in cols:
            cols["title"] = name
        if meta.get("type") == "date" and "date" not in cols:
            cols["date"] = name
        if meta.get("type") == "select" and "status" not in cols:
            cols["status"] = name
    log(f"Matched task DB columns: {cols}")
    return cols

# ---------------- query helpers ----------------
def query_database_by_date(dbid, date_prop_name, date_str):
    payload = {"filter": {"property": date_prop_name, "date": {"equals": date_str}}}
    r = notion_post(f"https://api.notion.com/v1/databases/{dbid}/query", payload)
    if r.status_code != 200:
        log(f"ERROR query_database_by_date {dbid}: {r.status_code} {r.text}")
        return []
    return r.json().get("results", [])

# ---------------- rollover (未完成任务顺延) ----------------
def rollover_unfinished_tasks():
    # get task DB info and match columns
    dbinfo = get_database_info(TASK_DB_ID)
    if not dbinfo:
        log("ERROR: 无法读取任务数据库信息")
        return
    cols = match_task_columns(dbinfo)
    if not cols.get("date") or not cols.get("status") or not cols.get("title"):
        log("ERROR: 任务数据库必须包含 date/title/status 列")
        return

    yesterday = (datetime.now(tz) - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_tasks = query_database_by_date(TASK_DB_ID, cols["date"], yesterday)
    log(f"检测到昨日任务 {len(yesterday_tasks)} 条，开始检测未完成并顺延...")
    rolled = []
    for p in yesterday_tasks:
        props = p.get("properties", {})
        status_sel = props.get(cols["status"], {}).get("select")
        title = ""
        title_field = props.get(cols["title"], {})
        if title_field.get("title"):
            title = title_field["title"][0].get("plain_text","")
        if not status_sel or status_sel.get("name") not in ("已完成","完成","Done","done"):
            # create a new page for today copying title and other useful props
            new_props = {}
            # copy title
            new_props[cols["title"]] = {"title":[{"text":{"content": title}}]}
            # set date -> today (use same date prop name)
            new_props[cols["date"]] = {"date":{"start": datetime.now(tz).strftime("%Y-%m-%d")}}
            # reset status to 未开始
            if cols.get("status"):
                new_props[cols["status"]] = {"select":{"name":"未开始"}}
            # copy resource if exists
            if cols.get("resource"):
                url_val = props.get(cols["resource"], {}).get("url")
                if url_val:
                    new_props[cols["resource"]] = {"url": url_val}
            # try to copy hint
            if cols.get("hint"):
                rt = props.get(cols["hint"], {}).get("rich_text", [])
                if rt:
                    new_props[cols["hint"]] = {"rich_text": rt}
            # create
            payload = {"parent":{"database_id": TASK_DB_ID}, "properties": new_props}
            r = notion_post("https://api.notion.com/v1/pages", payload)
            if r.status_code in (200,201):
                rolled.append(title)
            else:
                log(f"⚠ 无法顺延任务 “{title}”：{r.status_code} {r.text}")
    if rolled:
        log(f"↩️ 已顺延 {len(rolled)} 个任务到今日：{rolled}")
    else:
        log("✅ 无需顺延或顺延无失败项。")

# ---------------- create / update daily review ----------------
def find_review_entry_by_date(review_db_id, date_str):
    payload = {"filter": {"property":"📅 日期", "date":{"equals": date_str}}}
    r = notion_post(f"https://api.notion.com/v1/databases/{review_db_id}/query", payload)
    if r.status_code != 200:
        log(f"ERROR find_review_entry_by_date: {r.status_code} {r.text}")
        return None
    results = r.json().get("results", [])
    return results[0] if results else None

def create_daily_review_if_missing(review_db_id):
    # compute today's task stats
    dbinfo = get_database_info(TASK_DB_ID)
    cols = match_task_columns(dbinfo)
    if not cols.get("date") or not cols.get("status"):
        log("ERROR: 任务数据库缺失 date 或 status 列，无法统计今日任务")
        return False
    total, done = 0, 0
    tasks = query_database_by_date(TASK_DB_ID, cols["date"], TODAY)
    total = len(tasks)
    for t in tasks:
        sel = t["properties"].get(cols["status"], {}).get("select")
        if sel and sel.get("name") in ("已完成","完成","Done","done"):
            done += 1
    undone = total - done

    existing = find_review_entry_by_date(review_db_id, TODAY)
    if existing:
        # update counts but preserve rich_text fields (do not overwrite)
        page_id = existing["id"]
        update_payload = {}
        # if properties contain these names, update them
        update_payload["✅ 完成任务数"] = {"number": done}
        update_payload["❌ 未完成任务数"] = {"number": undone}
        r = notion_patch(f"https://api.notion.com/v1/pages/{page_id}", {"properties": update_payload})
        if r.status_code in (200,201):
            log(f"✅ 更新今日复盘数据：完成 {done} / 总 {total}")
            return True
        else:
            log(f"⚠ 更新今日复盘失败：{r.status_code} {r.text}")
            return False
    else:
        # create new daily review page
        props = {
            "名称": { "title": [ { "text": {"content": title_text} } ] },
            "日期": { "date": {"start": today} },
            "✅ 完成任务数": {"number": done},
            "❌ 未完成任务数": {"number": undone},
    "🪞 总结": {
        "rich_text": [
            {"text": {"content": "（请补充每日复盘）"}}
        ]
    },
    "⚠ 难点": {
        "rich_text": [
            {"text": {"content": "（请记录今日难点）"}}
        ]
    },
    "💡 解决方案": {
        "rich_text": [
            {"text": {"content": "（请填写解决方案）"}}
        ]
    },
    "🧩 类型": {
        "select": {"name": "每日复盘"}
    }
}
        r = notion_post("https://api.notion.com/v1/pages", {"parent":{"database_id": review_db_id}, "properties": props})
        if r.status_code in (200,201):
            log(f"🆕 创建今日复盘页面：{TODAY}（完成 {done} / {total}）")
            return True
        else:
            log(f"❌ 创建今日复盘失败：{r.status_code} {r.text}")
            return False

# ---------------- collect daily reviews for a date range ----------------
def collect_daily_reviews(review_db_id, start_date, end_date):
    payload = {
        "filter": {
            "and": [
                {"property":"📅 日期", "date":{"on_or_after": start_date}},
                {"property":"📅 日期", "date":{"on_or_before": end_date}}
            ]
        },
        "page_size": 100
    }
    r = notion_post(f"https://api.notion.com/v1/databases/{review_db_id}/query", payload)
    if r.status_code != 200:
        log(f"ERROR collect_daily_reviews: {r.status_code} {r.text}")
        return []
    items = r.json().get("results", [])
    # ensure they are of 类型 "每日" or empty
    filtered = []
    for it in items:
        t = it["properties"].get("类型", {}).get("select", {}).get("name","")
        if t in ("每日",""):
            filtered.append(it)
    return filtered

# ---------------- summarize keywords from reviews ----------------
def summarize_keywords(items, field_name="⚠ 难点", top_n=5):
    words = []
    for it in items:
        rt = it["properties"].get(field_name, {}).get("rich_text", [])
        text = "".join([x.get("plain_text","") for x in rt]) if rt else ""
        # basic splitting
        tokens = [w.strip() for w in text.replace("、"," ").replace(","," ").split() if w.strip()]
        words.extend(tokens)
    cnt = Counter(words)
    return cnt.most_common(top_n)

# ---------------- AI summary (optional) ----------------
def generate_ai_summary(prompt, model=OPENAI_MODEL):
    if not OPENAI_API_KEY:
        log("WARN: OPENAI_API_KEY 未设置，跳过 AI 总结")
        return "（AI 未启用）"
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type":"application/json"}
    payload = {
        "model": model,
        "messages": [{"role":"system","content":"你是一位执行教练，帮助总结关键结论与改进建议。"},
                     {"role":"user","content":prompt}],
        "temperature": 0.2,
        "max_tokens": 600
    }
    r = requests.post(url, headers=headers, json=payload)
    if r.status_code == 200:
        try:
            txt = r.json()["choices"][0]["message"]["content"].strip()
            return txt
        except Exception as e:
            log("AI parse error: " + str(e))
            return "（AI 返回解析失败）"
    else:
        log(f"AI 请求失败：{r.status_code} {r.text}")
        return "（AI 请求失败）"

# ---------------- create periodic review (weekly/monthly) ----------------
def create_periodic_review(review_db_id, start_date, end_date, kind="每周"):
    items = collect_daily_reviews(review_db_id, start_date, end_date)
    total_tasks = sum(int(it["properties"].get("✅ 完成任务数", {}).get("number") or 0) +
                      int(it["properties"].get("❌ 未完成任务数", {}).get("number") or 0)
                      for it in items)
    total_done = sum(int(it["properties"].get("✅ 完成任务数", {}).get("number") or 0) for it in items)
    avg_done = round((total_done / len(items)) if items else 0, 2)
    top = summarize_keywords(items)
    top_str = "; ".join([f"{k}({v}次)" for k,v in top]) if top else "无明显高频难点"

    prompt = f"""请为用户生成一份{kind}总结：
时间范围：{start_date} 到 {end_date}
共计天数：{len(items)}，完成任务总数：{total_done}，总任务数：{total_tasks}，平均每日完成：{avg_done}
高频难点：{top_str}
请输出：1) 关键结论 2) 改进建议 3) 一段 1-2 段落的总结语。"""
    ai_text = generate_ai_summary(prompt)

    props = {
        "📝 标题": {"title":[{"text":{"content": f"{kind} 复盘 {end_date}"}}]},
        "📅 日期": {"date":{"start": end_date}},
        "✅ 完成任务数": {"number": total_done},
        "❌ 未完成任务数": {"number": total_tasks - total_done},
        "⚠ 难点": {"rich_text":[{"text":{"content": top_str}}]},
        "💡 解决方案": {"rich_text":[{"text":{"content": "（自动汇总）\n" + ai_text}}]},
        "总结": {"rich_text":[{"text":{"content": ai_text}}]},
        "类型": {"select":{"name": "每周" if kind=="每周" else "每月"}}
    }
    r = notion_post("https://api.notion.com/v1/pages", {"parent": {"database_id": review_db_id}, "properties": props})
    if r.status_code in (200,201):
        log(f"✅ 已创建 {kind} 复盘：{end_date}")
    else:
        log(f"❌ 创建 {kind} 复盘失败：{r.status_code} {r.text}")

# ---------------- system_check ----------------
def system_check():
    try:
        log("🧠 系统自检开始...")
        # 1) 昨日未完成任务是否已顺延到今日
        yesterday = (datetime.now(tz) - timedelta(days=1)).strftime("%Y-%m-%d")
        dbinfo = get_database_info(TASK_DB_ID)
        if not dbinfo:
            log("❌ 无法读取 Task DB")
            return
        cols = match_task_columns(dbinfo)
        if not cols.get("date") or not cols.get("status") or not cols.get("title"):
            log("❌ Task DB 列匹配失败（需要 date/title/status）")
            return
        y_tasks = query_database_by_date(TASK_DB_ID, cols["date"], yesterday)
        unfinished = []
        for t in y_tasks:
            sel = t["properties"].get(cols["status"], {}).get("select")
            title = t["properties"].get(cols["title"], {}).get("title",[{}])[0].get("plain_text","")
            if not sel or sel.get("name") not in ("已完成","完成","Done","done"):
                unfinished.append(title)
        if unfinished:
            log(f"⚠ 昨日未完成任务（{len(unfinished)}）：{unfinished}")
            # check if present today
            today_tasks = query_database_by_date(TASK_DB_ID, cols["date"], TODAY)
            today_titles = [tt["properties"].get(cols["title"], {}).get("title",[{}])[0].get("plain_text","") for tt in today_tasks]
            not_roll = [x for x in unfinished if x not in today_titles]
            if not_roll:
                log(f"❌ 以下任务未顺延到今日：{not_roll}")
            else:
                log("✅ 所有未完成任务已顺延到今日")
        else:
            log("✅ 昨日全部任务已完成")

        # 2) 今日复盘是否存在
        if not DAILY_REVIEW_DB_ID:
            log("⚠ 未设置 DAILY_REVIEW_DB_ID（每日复盘数据库），无法检查")
        else:
            rev = find_review_entry_by_date(DAILY_REVIEW_DB_ID, TODAY)
            if rev:
                log("✅ 今日复盘已存在")
            else:
                log("⚠ 今日复盘尚未生成")

        # 3) 周/月 检查（只在周日或月末做）
        dnow = datetime.now(tz)
        if dnow.weekday() == 6:
            # check weekly
            log("🔍 当前为周日，检查周复盘")
            # we check existence of entry with 类型 每周 and date end = today
            if not CYCLE_REVIEW_DB_ID:
                log("⚠ 未设置 CYCLE_REVIEW_DB_ID（周/月复盘数据库）")
            else:
                payload = {"filter":{"and":[{"property":"类型","select":{"equals":"每周"}},{"property":"📅 日期","date":{"equals":TODAY}}]}}
                r = notion_post(f"https://api.notion.com/v1/databases/{CYCLE_REVIEW_DB_ID}/query", payload)
                if r.status_code == 200 and r.json().get("results"):
                    log("✅ 本周复盘已存在")
                else:
                    log("⚠ 本周复盘尚未生成")
        # month end check
        tomorrow = (datetime.now(tz) + timedelta(days=1)).strftime("%Y-%m-%d")
        if datetime.strptime(tomorrow, "%Y-%m-%d").month != datetime.now(tz).month:
            log("🔍 今日为月末，检查月复盘")
            if not CYCLE_REVIEW_DB_ID:
                log("⚠ 未设置 CYCLE_REVIEW_DB_ID（周/月复盘数据库）")
            else:
                payload = {"filter":{"and":[{"property":"类型","select":{"equals":"每月"}},{"property":"📅 日期","date":{"equals":TODAY}}]}}
                r = notion_post(f"https://api.notion.com/v1/databases/{CYCLE_REVIEW_DB_ID}/query", payload)
                if r.status_code == 200 and r.json().get("results"):
                    log("✅ 本月复盘已存在")
                else:
                    log("⚠ 本月复盘尚未生成")
        log("🧩 系统自检完成")
    except Exception as e:
        log("❌ 系统自检异常: " + str(e))
        traceback.print_exc()

# ---------------- main flow ----------------
def main_flow():
    log("开始 v8 自动复盘主流程")
    # ensure review DB fields exist (if configured)
    daily_required = {
        "📝 标题":{"title":{}},
        "📅 日期":{"date":{}},
        "✅ 完成任务数":{"number":{}},
        "❌ 未完成任务数":{"number":{}},
        "⚠ 难点":{"rich_text":{}},
        "💡 解决方案":{"rich_text":{}},
        "总结":{"rich_text":{}},
        "类型":{"select":{"options":[{"name":"每日"},{"name":"每周"},{"name":"每月"}]}}
    }
    if DAILY_REVIEW_DB_ID:
        ensure_props_on_db(DAILY_REVIEW_DB_ID, daily_required)
    if CYCLE_REVIEW_DB_ID:
        ensure_props_on_db(CYCLE_REVIEW_DB_ID, daily_required)

    # 1. rollover yesterday unfinished -> today
    rollover_unfinished_tasks()

    # 2. create or update today's daily review
    if DAILY_REVIEW_DB_ID:
        create_daily_review_if_missing(DAILY_REVIEW_DB_ID)
    else:
        log("⚠ 未配置 DAILY_REVIEW_DB_ID，跳过每日复盘写入")

    # 3. weekly/monthly periodic creation
    dnow = datetime.now(tz)
    if dnow.weekday() == 6 and CYCLE_REVIEW_DB_ID:
        # weekly: last 7 days
        start = (dnow - timedelta(days=6)).strftime("%Y-%m-%d")
        end = dnow.strftime("%Y-%m-%d")
        create_periodic_review(CYCLE_REVIEW_DB_ID, start, end, kind="每周")
    # if month end
    tomorrow = (dnow + timedelta(days=1)).strftime("%Y-%m-%d")
    if datetime.strptime(tomorrow, "%Y-%m-%d").month != dnow.month and CYCLE_REVIEW_DB_ID:
        start = dnow.replace(day=1).strftime("%Y-%m-%d")
        end = dnow.strftime("%Y-%m-%d")
        create_periodic_review(CYCLE_REVIEW_DB_ID, start, end, kind="每月")

    log("主流程完成。")

# ---------------- schedule ----------------
def run_scheduler():
    # schedule main_flow at 00:00 (rollover) and 23:55 (daily review + periodic)
    schedule.clear()
    schedule.every().day.at(cfg.get("ROLLOVER_TIME","00:00")).do(lambda: (system_check(), rollover_unfinished_tasks()))
    schedule.every().day.at(cfg.get("DAILY_REVIEW_TIME","23:55")).do(lambda: (system_check(), main_flow()))
    log("调度已设置：每日顺延时间 %s，复盘时间 %s" % (cfg.get("ROLLOVER_TIME","00:00"), cfg.get("DAILY_REVIEW_TIME","23:55")))
    # run loop
    while True:
        schedule.run_pending()
        import time
        time.sleep(10)

# ---------------- CLI util for manual run ----------------
def run_now():
    system_check()
    main_flow()

# ---------------- entry ----------------
if __name__ == "__main__":
    log("启动 Notion 智能复盘系统 v8")
    # quick checks
    try:
        run_now()
    except Exception as e:
        log("主流程异常: " + str(e))
        traceback.print_exc()
    # if user wants continuous scheduler, uncomment below:
    if cfg.get("ENABLE_SCHEDULER", False):
        run_scheduler()
        import schedule, time

def job():
    print("⏰ 每日自动复盘开始...")
    main()