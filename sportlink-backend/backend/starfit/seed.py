"""Idempotent demo-data initializer and the 32-item exercise knowledge base.

Every demo row is explicitly marked as demo data. Media URLs are intentionally
empty strings: no fake video/3D resource links are invented. Run explicitly with
`python -m backend.starfit.seed [--reset]`; the app also calls
ensure_demo_data() on startup when SOLOPILOT_STARFIT_SEED_DEMO is true.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from .. import db
from .auth import hash_password
from .schema import ensure_schema, clear_all

DEMO_PASSWORD = "demo123456"

# category -> list of exercise dicts. 8 categories x 4 = 32 actions.
_EX: list[dict[str, Any]] = []


def _ex(
    ex_id: str,
    name: str,
    category: str,
    min_age: int,
    max_age: int,
    difficulty: str,
    goal: str,
    instructions: list[str],
    mistakes: list[str],
    equipment: list[str],
    safety: str,
    tags: list[str],
) -> None:
    _EX.append(
        {
            "id": ex_id,
            "name": name,
            "category": category,
            "minAge": min_age,
            "maxAge": max_age,
            "difficulty": difficulty,
            "trainingGoal": goal,
            "instructions": json.dumps(instructions, ensure_ascii=False),
            "commonMistakes": json.dumps(mistakes, ensure_ascii=False),
            "equipment": json.dumps(equipment, ensure_ascii=False),
            "safetyNotes": safety,
            "videoUrl": "",
            "model3dUrl": "",
            "tags": json.dumps(tags, ensure_ascii=False),
        }
    )


# ---- 平衡训练 ----
_ex("ex_bal_01", "单脚站立", "平衡训练", 5, 12, "入门", "静态平衡与本体感觉",
    ["双脚并拢站立，双手侧平举", "抬起一只脚，膝盖微屈，保持 10-20 秒", "换脚重复，每侧 3 组"],
    ["身体大幅摇晃时仍硬撑", "憋气", "支撑腿完全锁死"], ["瑜伽垫"],
    "旁边需要有成人保护，地面防滑；头晕或疼痛立即停止。", ["平衡", "入门", "无器械"])
_ex("ex_bal_02", "平衡垫站立", "平衡训练", 6, 12, "进阶", "不稳定平面上的平衡控制",
    ["站在软平衡垫中央", "保持躯干直立，目视前方一点", "逐渐尝试闭眼 5 秒，每次 3 组"],
    ["低头看脚", "膝盖内扣", "在无人保护下闭眼"], ["平衡垫"],
    "必须有成人近距离保护，避免在硬物旁练习。", ["平衡", "进阶", "器械"])
_ex("ex_bal_03", "燕式平衡", "平衡训练", 7, 12, "进阶", "动态平衡与髋部稳定",
    ["单脚站立，另一腿向后伸直", "上身前倾，双臂前伸与地面平行", "保持 5-10 秒后换边"],
    ["腰部过度下塌", "支撑脚翻转", "追求时长而牺牲姿态"], ["瑜伽垫"],
    "腰背不适者不做；保持空间空旷。", ["平衡", "协调", "进阶"])
_ex("ex_bal_04", "直线蟹行", "平衡训练", 5, 10, "入门", "侧向移动中的重心控制",
    ["在地上贴一条直线", "双脚不交叉沿直线侧向移动", "往返 5 趟，保持上身稳定"],
    ["交叉步", "速度过快", "含胸驼背"], ["地面胶带"],
    "清理地面障碍物，穿防滑鞋。", ["平衡", "敏捷", "亲子"])

# ---- 协调性训练 ----
_ex("ex_coo_01", "开合跳", "协调性训练", 5, 12, "入门", "上下肢节奏协调",
    ["双脚并拢、双手垂于体侧", "跳起时双脚分开、双手头顶击掌", "落回原位，连续 15-20 次"],
    ["落地全脚掌砸地", "手臂与腿不同步", "膝盖内扣"], ["瑜伽垫"],
    "落地轻缓，膝踝不适者减量或改做无跳版本。", ["协调", "热身", "无器械"])
_ex("ex_coo_02", "交叉步", "协调性训练", 6, 12, "入门", "左右交叉的肢体协调",
    ["站立，右脚向左前方交叉迈出", "左脚跟上，再反向交叉", "左右交替 10 次为一组"],
    ["步幅过大", "上身扭转过度", "节奏忽快忽慢"], [],
    "地面防滑，避免在湿滑地面练习。", ["协调", "步法"])
_ex("ex_coo_03", "手脚交替拍", "协调性训练", 5, 10, "入门", "交叉 midline 协调",
    ["站立，右手拍左膝、左手拍右膝", "交替加快节奏", "30 秒一组，做 3 组"],
    ["同侧手脚相拍", "弯腰驼背", "只求速度"], [],
    "无需器械，注意周围空间。", ["协调", "感统", "亲子"])
_ex("ex_coo_04", "跳绳基础", "协调性训练", 6, 12, "进阶", "手眼脚节奏配合",
    ["双手握绳，绳置于身后", "手腕发力摇绳，双脚轻跳过绳", "先连续 10 次，逐步增加到 30 次"],
    ["全手臂抡绳", "跳得过高", "落地过重"], ["跳绳"],
    "选择长度合适的绳子，穿运动鞋，避开坚硬地面。", ["协调", "耐力", "器械"])

# ---- 敏捷训练 ----
_ex("ex_agi_01", "敏捷梯小碎步", "敏捷训练", 6, 12, "入门", "步频与脚步精准度",
    ["将敏捷梯平铺于地面", "每格一步快速通过", "往返 4 趟，逐步提速"],
    ["踩到梯框", "步幅忽大忽小", "低头看脚"], ["敏捷梯"],
    "梯面必须贴平，避免绊倒。", ["敏捷", "步法", "器械"])
_ex("ex_agi_02", "折返跑", "敏捷训练", 7, 12, "进阶", "加速、减速与变向",
    ["相距 5-10 米放两个标志物", "跑到对面触摸标志物后折返", "完成 4 个来回为一组"],
    ["变向时未降重心", "全程全速不减速", "标志物距离过短"], ["标志盘"],
    "充分热身，地面防滑；心率异常立即停止。", ["敏捷", "速度", "进阶"])
_ex("ex_agi_03", "侧向滑步", "敏捷训练", 6, 12, "入门", "侧向移动与重心转移",
    ["半蹲准备，双脚略宽于肩", "向右滑出两步再向左滑回", "保持上身高度稳定，做 3 组"],
    ["双脚并拢跳", "上身起伏大", "膝盖超过脚尖过多"], [],
    "场地空旷，避免碰撞。", ["敏捷", "篮球", "步法"])
_ex("ex_agi_04", "反应球抓握", "敏捷训练", 6, 12, "入门", "视觉反应与手眼协调",
    ["成人将反应球轻抛向地面", "孩子观察弹起方向并抓握", "每轮 10 次"],
    ["抛球过猛", "在硬地或靠墙处练习", "多人同时抢球"], ["反应球"],
    "使用软质球，保持安全距离。", ["敏捷", "反应", "亲子"])

# ---- 基础力量 ----
_ex("ex_str_01", "自重深蹲", "基础力量", 7, 12, "入门", "下肢基础力量",
    ["双脚与肩同宽站立", "臀部向后坐、膝盖对齐脚尖下蹲", "站起还原，10 次一组"],
    ["膝盖内扣", "脚跟离地", "弯腰前扑"], [],
    "不追求深度，膝痛立即停止；不做负重。", ["力量", "下肢", "无器械"])
_ex("ex_str_02", "熊爬", "基础力量", 5, 10, "入门", "核心与肩髋协同",
    ["四点支撑，膝盖离地约 5 厘米", "对侧手脚同时向前移动", "爬行 3-5 米为一组"],
    ["腰部下塌", "臀部抬得过高", "速度快到失控"], ["瑜伽垫"],
    "手腕不适可改前臂支撑版本。", ["力量", "核心", "亲子"])
_ex("ex_str_03", "平板支撑", "基础力量", 7, 12, "进阶", "核心稳定",
    ["俯卧，前臂与脚尖支撑", "耳、肩、髋、踝成一条直线", "保持 15-30 秒，做 3 组"],
    ["塌腰或撅臀", "憋气", "追求时长导致变形"], ["瑜伽垫"],
    "腰背疼痛者不做；保持自然呼吸。", ["力量", "核心", "进阶"])
_ex("ex_str_04", "臀桥", "基础力量", 6, 12, "入门", "臀部与后链激活",
    ["仰卧屈膝，双脚平放", "收紧臀部把髋部抬起", "顶点停 2 秒后落下，12 次一组"],
    ["用腰顶起", "脚跟离地太远", "颈部发力"], ["瑜伽垫"],
    "颈部放松，动作缓慢可控。", ["力量", "后链", "入门"])

# ---- 基础耐力 ----
_ex("ex_end_01", "原地高抬腿", "基础耐力", 6, 12, "入门", "心肺耐力与节奏",
    ["原地站立，交替抬膝至髋部高度", "手臂配合摆动", "30 秒一组，做 3 组"],
    ["后仰", "抬膝不足", "落地过重"], [],
    "控制强度，出现气喘过度立即休息。", ["耐力", "热身", "无器械"])
_ex("ex_end_02", "间歇快走慢跑", "基础耐力", 7, 12, "入门", "基础有氧耐力",
    ["快走 1 分钟", "慢跑 30 秒", "交替循环 6-8 轮"],
    ["一开始就冲刺", "不补水", "在不平路面跑"], [],
    "选择平整场地，穿合适跑鞋，按需补水。", ["耐力", "有氧"])
_ex("ex_end_03", "连续跳绳", "基础耐力", 7, 12, "进阶", "持续心肺负荷",
    ["以稳定节奏连续跳绳", "目标 60-90 秒不间断", "组间休息 60 秒，做 3 组"],
    ["跳得过高", "手腕僵硬", "疲劳后仍强行坚持"], ["跳绳"],
    "疲劳导致动作变形时应停止。", ["耐力", "协调", "器械"])
_ex("ex_end_04", "动物模仿爬行接力", "基础耐力", 5, 9, "入门", "趣味性持续活动",
    ["设定 5 米路线", "依次模仿熊爬、螃蟹走、青蛙跳", "往返一轮为一组，做 3 组"],
    ["动作过猛碰撞", "在硬地跳跃", "无成人看护"], ["瑜伽垫"],
    "全程成人看护，控制人数避免碰撞。", ["耐力", "亲子", "游戏"])

# ---- 篮球基础 ----
_ex("ex_bas_01", "原地拍球", "篮球基础", 5, 10, "入门", "球感与手眼协调",
    ["双脚开立，膝微屈", "用指腹按压球，球弹至腰部高度", "左右手各 20 次"],
    ["用手掌拍球", "低头看球", "站姿过直"], ["篮球"],
    "使用适合儿童尺寸的篮球，场地空旷。", ["篮球", "球感", "入门"])
_ex("ex_bas_02", "行进间运球", "篮球基础", 7, 12, "进阶", "移动中的控球",
    ["沿直线慢走并运球", "球落在身体侧前方", "逐步过渡到慢跑，往返 4 趟"],
    ["运球过高", "看球不看路", "用力过猛"], ["篮球", "标志盘"],
    "确认路线无障碍，避免与其他人相撞。", ["篮球", "控球", "进阶"])
_ex("ex_bas_03", "双手胸前传球", "篮球基础", 6, 12, "入门", "传球发力与接球",
    ["双手持球于胸前，肘微屈", "蹬地伸臂将球推出，手指拨球", "与搭档相距 2-3 米互传 20 次"],
    ["用掌心推球", "传球过高", "接球时手指前伸硬接"], ["篮球"],
    "接球时屈肘缓冲，保持适当距离。", ["篮球", "传球", "亲子"])
_ex("ex_bas_04", "定点投篮", "篮球基础", 7, 12, "进阶", "投篮动作定型",
    ["站在篮下 1.5-2 米处", "屈膝蹬地、手臂向上伸展拨球", "每点 10 次，逐步后移"],
    ["只用手臂发力", "肘部外翻", "距离过远导致动作变形"], ["篮球", "儿童篮架"],
    "使用适合身高的篮架，避免争抢篮板碰撞。", ["篮球", "投篮", "进阶"])

# ---- 跳跃训练 ----
_ex("ex_jum_01", "双脚纵跳", "跳跃训练", 5, 10, "入门", "下肢爆发力与落地缓冲",
    ["双脚与肩同宽，屈膝预蹲", "双臂上摆带动身体向上跳", "落地屈膝缓冲，8 次一组"],
    ["直腿落地", "落地内扣", "连续跳跃不休息"], ["瑜伽垫"],
    "落地必须屈膝缓冲，踝膝不适者减量。", ["跳跃", "爆发力", "入门"])
_ex("ex_jum_02", "立定跳远", "跳跃训练", 6, 12, "入门", "水平方向爆发力",
    ["双脚并拢站在起跳线后", "摆臂蹬地向前跳出", "落地站稳后测量距离，6 次一组"],
    ["起跳前垫步", "落地后手撑地", "在光滑地面跳"], ["卷尺", "地面胶带"],
    "落地区域必须防滑、无杂物。", ["跳跃", "爆发力"])
_ex("ex_jum_03", "跳格子", "跳跃训练", 5, 10, "入门", "跳跃节奏与空间感",
    ["用胶带在地面贴出 6-8 个格子", "双脚依次跳入每格", "往返 3 趟"],
    ["格子间距过大", "单双脚混乱导致失衡", "速度过快"], ["地面胶带"],
    "胶带边缘贴牢，避免绊脚。", ["跳跃", "协调", "游戏"])
_ex("ex_jum_04", "单脚跳接力", "跳跃训练", 7, 12, "进阶", "单侧稳定与力量",
    ["设定 5 米路线", "单脚连续跳至终点，换脚跳回", "每侧 2 趟"],
    ["落地全脚掌砸地", "膝盖内扣", "疲劳后继续"], ["标志盘"],
    "仅供具备基础平衡能力儿童，成人看护。", ["跳跃", "平衡", "进阶"])

# ---- 亲子互动运动 ----
_ex("ex_par_01", "亲子传球", "亲子互动运动", 5, 10, "入门", "互动与接球反应",
    ["家长与孩子相距 2 米站立", "用软球互相轻抛接住", "连续 20 次不落地为一组"],
    ["抛球过猛", "距离过近", "使用硬质球"], ["软球"],
    "使用软质球，避免砸向面部。", ["亲子", "反应", "入门"])
_ex("ex_par_02", "镜像模仿游戏", "亲子互动运动", 5, 9, "入门", "观察与动作模仿",
    ["家长做一个缓慢动作", "孩子像镜子一样同步模仿", "轮换领做，每次 3 分钟"],
    ["动作过快", "做危险动作", "强行拉伸"], [],
    "只做温和的大动作，避免拉伸与搬抬。", ["亲子", "协调", "游戏"])
_ex("ex_par_03", "毛巾双人拔河", "亲子互动运动", 6, 12, "入门", "对抗中的核心稳定",
    ["两人各握毛巾一端，双脚前后开立", "听口令轻拉，保持身体不后仰", "每轮 10 秒，做 5 轮"],
    ["突然猛拉", "松手导致对方摔倒", "在硬地附近进行"], ["毛巾"],
    "必须听口令同时发力/松开，周围留空。", ["亲子", "力量", "游戏"])
_ex("ex_par_04", "亲子树式", "亲子互动运动", 5, 10, "入门", "共同平衡与专注",
    ["两人并排站立，内侧手轻扶", "外侧脚抬起贴于支撑腿内侧", "共同保持 10 秒后换边"],
    ["互相用力拉扯", "闭眼", "在湿滑地面做"], ["瑜伽垫"],
    "互相只轻扶不拉拽，失衡时立即放下脚。", ["亲子", "平衡", "入门"])


def _write_all(conn: Any) -> None:
    now = db.now_ms()

    users = [
        ("u_parent_demo", "13800000001", "林女士（演示）", "PARENT"),
        ("u_parent_other", "13800000002", "陈先生（演示）", "PARENT"),
        ("u_coach_wang", "13900000001", "王教练（演示）", "COACH"),
        ("u_coach_li", "13900000002", "李教练（演示）", "COACH"),
        ("u_coach_zhang", "13900000003", "张教练（演示）", "COACH"),
        ("u_admin", "13700000000", "平台管理员（演示）", "ADMIN"),
    ]
    pwd = hash_password(DEMO_PASSWORD)
    for uid, phone, name, role in users:
        conn.execute(
            'INSERT OR IGNORE INTO "sf_user" '
            '("id","phone","name","passwordHash","role","status","createdAt","updatedAt") '
            "VALUES (?,?,?,?,?,'ACTIVE',?,?)",
            (uid, phone, name, pwd, role, now, now),
        )

    children = [
        ("c_xingxing", "u_parent_demo", "小星", 8, ["篮球", "平衡训练"], ["提升协调性", "篮球基础"]),
        ("c_xiaoyue", "u_parent_demo", "小跃", 6, ["亲子互动运动", "跳跃训练"], ["打好运动基础"]),
        ("c_other", "u_parent_other", "别的孩子", 9, ["足球"], ["基础耐力"]),
    ]
    for cid, guardian, nickname, age, interests, goals in children:
        conn.execute(
            'INSERT OR IGNORE INTO "sf_child" '
            '("id","guardianId","nickname","age","sportsInterests","trainingGoals","createdAt","updatedAt") '
            "VALUES (?,?,?,?,?,?,?,?)",
            (cid, guardian, nickname, age, json.dumps(interests, ensure_ascii=False),
             json.dumps(goals, ensure_ascii=False), now, now),
        )
        conn.execute(
            'INSERT OR IGNORE INTO "sf_guardian_relationship" '
            '("id","childId","userId","relationship","createdAt") VALUES (?,?,?,?,?)',
            (db.new_id("gr"), cid, guardian, "GUARDIAN", now),
        )

    coaches = [
        ("coach_wang", "u_coach_wang", "王教练", ["鼓楼区", "台江区"], ["篮球基础", "敏捷训练"], 19900,
         "6 年儿童篮球启蒙教学经验，擅长用游戏带动基础动作。"),
        ("coach_li", "u_coach_li", "李教练", ["仓山区", "鼓楼区"], ["平衡训练", "协调性训练"], 17900,
         "儿童体适能与感统协调方向，注重安全与循序渐进。"),
        ("coach_zhang", "u_coach_zhang", "张教练", ["仓山区", "台江区"], ["基础耐力", "基础力量"], 15900,
         "专注 6-12 岁基础体能，课程以趣味循环站为主。"),
    ]
    for cid, uid, name, areas, types, price, bio in coaches:
        conn.execute(
            'INSERT OR IGNORE INTO "sf_coach" '
            '("id","userId","name","serviceAreas","courseTypes","priceCents","bio",'
            '"certificateStatus","avatarUrl","createdAt","updatedAt") '
            "VALUES (?,?,?,?,?,?,?,'APPROVED','',?,?)",
            (cid, uid, name, json.dumps(areas, ensure_ascii=False),
             json.dumps(types, ensure_ascii=False), price, bio, now, now),
        )

    services = [
        ("svc_basketball", "coach_wang", "篮球启蒙体验课", "篮球基础", 5, 12, 19900, 60, "一对一上门，球感、运球与投篮启蒙。"),
        ("svc_agility", "coach_wang", "敏捷梯专项课", "敏捷训练", 6, 12, 21900, 45, "步频、变向与反应训练。"),
        ("svc_balance", "coach_li", "平衡与协调课", "平衡训练", 5, 12, 17900, 60, "平衡、本体感觉与协调性练习。"),
        ("svc_coord", "coach_li", "感统协调游戏课", "协调性训练", 5, 10, 16900, 45, "以游戏形式完成协调性训练。"),
        ("svc_fitness", "coach_zhang", "儿童体适能基础课", "基础耐力", 6, 12, 15900, 60, "基础力量与耐力的趣味循环训练。"),
    ]
    for sid, coach, title, sport, amin, amax, price, duration, desc in services:
        conn.execute(
            'INSERT OR IGNORE INTO "sf_service" '
            '("id","coachId","title","sportType","ageMin","ageMax","priceCents",'
            '"durationMinutes","description","status","createdAt") '
            "VALUES (?,?,?,?,?,?,?,?,?,'ACTIVE',?)",
            (sid, coach, title, sport, amin, amax, price, duration, desc, now),
        )

    slots = [
        ("slot_w1", "coach_wang", "2026-11-14T09:00:00+08:00", "2026-11-14T10:00:00+08:00"),
        ("slot_w2", "coach_wang", "2026-11-14T15:00:00+08:00", "2026-11-14T16:00:00+08:00"),
        ("slot_w3", "coach_wang", "2026-11-15T10:00:00+08:00", "2026-11-15T11:00:00+08:00"),
        ("slot_l1", "coach_li", "2026-11-14T10:00:00+08:00", "2026-11-14T11:00:00+08:00"),
        ("slot_l2", "coach_li", "2026-11-15T14:00:00+08:00", "2026-11-15T15:00:00+08:00"),
        ("slot_z1", "coach_zhang", "2026-11-15T09:00:00+08:00", "2026-11-15T10:00:00+08:00"),
        ("slot_z2", "coach_zhang", "2026-11-15T16:00:00+08:00", "2026-11-15T17:00:00+08:00"),
    ]
    for sid, coach, start, end in slots:
        conn.execute(
            'INSERT OR IGNORE INTO "sf_coach_availability" '
            '("id","coachId","startAt","endAt","status","createdAt") VALUES (?,?,?,?,?,?)',
            (sid, coach, db.iso_to_ms(start), db.iso_to_ms(end), "OPEN", now),
        )

    for e in _EX:
        conn.execute(
            'INSERT OR IGNORE INTO "sf_exercise" '
            '("id","name","category","minAge","maxAge","difficulty","trainingGoal",'
            '"instructions","commonMistakes","equipment","safetyNotes","videoUrl",'
            '"model3dUrl","tags") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (e["id"], e["name"], e["category"], e["minAge"], e["maxAge"], e["difficulty"],
             e["trainingGoal"], e["instructions"], e["commonMistakes"], e["equipment"],
             e["safetyNotes"], e["videoUrl"], e["model3dUrl"], e["tags"]),
        )

    videos = [
        ("vid_01", "单脚站立动作讲解", "平衡训练", "ex_bal_01"),
        ("vid_02", "开合跳标准示范", "协调性训练", "ex_coo_01"),
        ("vid_03", "敏捷梯小碎步", "敏捷训练", "ex_agi_01"),
        ("vid_04", "自重深蹲要点", "基础力量", "ex_str_01"),
        ("vid_05", "原地拍球入门", "篮球基础", "ex_bas_01"),
        ("vid_06", "双脚纵跳与落地缓冲", "跳跃训练", "ex_jum_01"),
    ]
    for vid, title, category, ex_id in videos:
        conn.execute(
            'INSERT OR IGNORE INTO "sf_video" '
            '("id","title","category","exerciseId","ageMin","ageMax","videoUrl",'
            '"thumbnailUrl","durationSeconds","createdAt") VALUES (?,?,?,?,5,12,\'\',\'\',0,?)',
            (vid, title, category, ex_id, now),
        )

    # 教练布置的家庭训练任务（Motion Coach 模式 B 的默认素材）
    tasks = [
        ("ft_demo_xingxing", "c_xingxing", "coach_wang", "本周家庭训练：协调性 + 力量",
         [
             {"name": "自重深蹲", "exerciseId": "ex_str_01", "reps": 8, "sets": 2},
             {"name": "开合跳", "exerciseId": "ex_coo_01", "reps": 10, "sets": 2},
             {"name": "单脚站立", "exerciseId": "ex_bal_01", "seconds": 20},
         ], 3, "OPEN"),
        ("ft_demo_xiaoyue", "c_xiaoyue", "coach_li", "本周家庭训练：平衡入门",
         [
             {"name": "单脚站立", "exerciseId": "ex_bal_01", "seconds": 15},
             {"name": "开合跳", "exerciseId": "ex_coo_01", "reps": 8, "sets": 1},
         ], 2, "OPEN"),
    ]
    for tid, child, coach, title, items, goal, status in tasks:
        conn.execute(
            'INSERT OR IGNORE INTO "sf_family_task" '
            '("id","childId","bookingId","coachId","title","itemsJson","goalCount","status","createdAt") '
            "VALUES (?,?,NULL,?,?,?,?,?,?)",
            (tid, child, coach, title, json.dumps(items, ensure_ascii=False), goal, status, now),
        )


def ensure_demo_data() -> bool:
    """Seed only when the user table is empty. Returns True if data was written."""
    with db.get_conn() as conn:
        count = conn.execute('SELECT COUNT(*) FROM "sf_user"').fetchone()[0]
        if count:
            return False
        _write_all(conn)
    return True


def reset_demo_data() -> None:
    """Test/CLI helper: wipe sf_* rows and rebuild the demo dataset."""
    clear_all()
    with db.get_conn() as conn:
        _write_all(conn)


def main() -> None:
    ensure_schema()
    if "--reset" in sys.argv:
        reset_demo_data()
        action = "已清空并重建演示数据"
    else:
        action = "已写入演示数据" if ensure_demo_data() else "演示数据已存在，未改动（使用 --reset 重建）"
    with db.get_conn() as conn:
        summary = {
            "users": conn.execute('SELECT COUNT(*) FROM "sf_user"').fetchone()[0],
            "children": conn.execute('SELECT COUNT(*) FROM "sf_child"').fetchone()[0],
            "coaches": conn.execute('SELECT COUNT(*) FROM "sf_coach"').fetchone()[0],
            "services": conn.execute('SELECT COUNT(*) FROM "sf_service"').fetchone()[0],
            "availability": conn.execute('SELECT COUNT(*) FROM "sf_coach_availability"').fetchone()[0],
            "exercises": conn.execute('SELECT COUNT(*) FROM "sf_exercise"').fetchone()[0],
            "videos": conn.execute('SELECT COUNT(*) FROM "sf_video"').fetchone()[0],
        }
    print(f"StarFit seed: {action}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"演示账号密码统一为: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
