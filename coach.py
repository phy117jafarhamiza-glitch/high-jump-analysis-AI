"""
واجهة اللاعب والسلامة:
  - الملاحظة الأهم للاعب (ملاحظة واحدة في كل جلسة)
  - وحدة اليوم من البرنامج
  - الجاهزية والألم وقواعد الإيقاف/التخفيف
  - الحمل التدريبي (sRPE) ونسبة الحمل الحاد إلى المزمن (ACWR)
  - فحص جودة التصوير
"""
from datetime import date, datetime

import numpy as np
import pandas as pd

import model

PAIN_SITES = ["لا يوجد", "الركبة", "الكاحل/القدم", "أسفل الظهر", "الورك", "الفخذ الخلفية", "الساق/وتر أخيل", "الكتف", "أخرى"]
LOWER = {"الركبة", "الكاحل/القدم", "أسفل الظهر", "الورك", "الفخذ الخلفية", "الساق/وتر أخيل"}
JUMP_TYPES = {"بلايومتري"}
JUMP_UNITS = ("تكرار", "حاجز", "حجلة")


def main_cue(bank, error_ids):
    """أهم خطأ حسب الأولوية + رسالة بسيطة + تمرين تكنيكي واحد."""
    info = model.error_info(bank, [e for e in error_ids if e])
    if info.empty:
        return None
    e = info.iloc[0]
    msg = e.get("رسالة_للاعب") if "رسالة_للاعب" in info.columns else None
    if msg is None or (isinstance(msg, float) and np.isnan(msg)) or not str(msg).strip():
        msg = e.get("الوصف", "")
    ex = bank["exercises"]
    tech = ex[(ex["رمز_الخطأ"] == e["رمز_الخطأ"]) & (ex["النوع"] == "تكنيك")]
    drill = tech.iloc[0] if not tech.empty else None
    return {"id": e["رمز_الخطأ"], "name": e["الخطأ"], "message": str(msg),
            "drill": None if drill is None else str(drill["التمرين"]),
            "cue": None if drill is None else str(drill.get("النقطة_التعليمية", "")), "others": len(info) - 1}


def latest_errors(analyses, code):
    if analyses.empty or "code" not in analyses or "errors_final" not in analyses:
        return []
    a = analyses[analyses["code"].astype(str) == str(code)]
    if a.empty:
        return []
    last = a.iloc[-1]
    return [x for x in str(last.get("errors_final", "") or "").split(",") if x and x != "nan"]


def current_week(start, weeks, today=None):
    today = today or date.today()
    if isinstance(start, str):
        start = datetime.strptime(start[:10], "%Y-%m-%d").date()
    w = (today - start).days // 7 + 1
    return int(min(max(w, 1), weeks)), (today - start).days < 0, w > weeks


def readiness(sleep, fatigue, soreness, mood):
    """كل بند من 1 (سيئ) إلى 5 (ممتاز). يعيد النسبة المئوية."""
    return round((sleep + fatigue + soreness + mood - 4) / 16 * 100)


def safety_decision(pain_site, pain_level, ready_pct, acwr):
    """يعيد: الحالة (stop/reduce/ok)، معامل الحجم، الأنواع المحذوفة، الرسائل."""
    msgs, drop, factor, status = [], set(), 1.0, "ok"
    lower = pain_site in LOWER
    if pain_level >= 7:
        return "stop", 0.0, {"*"}, [f"ألم شديد ({pain_level}/10) في {pain_site}: أوقف التدريب اليوم وراجع طبيباً أو معالجاً رياضياً."]
    if lower and pain_level >= 4:
        status = "reduce"
        drop |= {"بلايومتري", "سرعة"}
        factor = min(factor, 0.5)
        msgs.append(f"ألم متوسط ({pain_level}/10) في {pain_site}: حُذفت تمرينات القفز والسرعة وخُفّض الحجم إلى النصف. "
                    "إذا استمر الألم أكثر من يومين راجع مختصاً.")
    elif pain_level >= 1 and pain_site != "لا يوجد":
        status = "reduce"
        factor = min(factor, 0.7)
        msgs.append(f"ألم خفيف في {pain_site}: خُفّض حجم التمرينات 30%. أوقف التمرين فوراً إذا زاد الألم.")
    if ready_pct < 40:
        status = "reduce"
        factor = min(factor, 0.6)
        drop |= {"بلايومتري"}
        msgs.append(f"جاهزيتك منخفضة ({ready_pct}%): جلسة خفيفة اليوم بدون قفز عالي الشدة، وركّز على النوم والتغذية.")
    elif ready_pct < 60:
        status = "reduce" if status == "ok" else status
        factor = min(factor, 0.8)
        msgs.append(f"جاهزيتك متوسطة ({ready_pct}%): خُفّض الحجم 20%.")
    if acwr is not None and not np.isnan(acwr):
        if acwr > 1.5:
            status = "reduce" if status == "ok" else status
            factor = min(factor, 0.7)
            msgs.append(f"حملك التدريبي هذا الأسبوع ارتفع بسرعة (نسبة الحمل {acwr:.2f} > 1.5): خطر إصابة أعلى، خُفّض الحجم.")
        elif acwr < 0.8:
            msgs.append(f"حملك التدريبي منخفض مقارنة بالأسابيع السابقة (نسبة الحمل {acwr:.2f}).")
    return status, factor, drop, msgs


def adjust_items(items, factor, drop):
    out = []
    for it in items:
        if "*" in drop or it["النوع"] in drop:
            continue
        it = dict(it)
        if factor < 1 and it["النوع"] not in ("إحماء", "تهدئة"):
            it["الجرعة"] = f"{it['الجرعة']}  ← خفّض إلى {int(factor * 100)}%"
        out.append(it)
    return out


def jump_count(items, factor=1.0):
    n = 0
    for it in items:
        if it["النوع"] not in JUMP_TYPES:
            continue
        dose = it["الجرعة"].split("←")[0]
        nums = [int(x) for x in dose.replace("×", " ").split() if x.isdigit()]
        if not nums or not any(u in dose for u in JUMP_UNITS):
            continue
        n += (nums[0] * nums[1]) if len(nums) >= 2 else nums[0]
    return int(round(n * factor))


def load_metrics(wellness, code, today=None):
    """sRPE الأسبوعي، ونسبة الحمل الحاد (7 أيام) إلى المزمن (متوسط 28 يوماً)."""
    today = pd.Timestamp(today or date.today())
    if wellness.empty or "code" not in wellness or "srpe" not in wellness:
        return {"acute": 0.0, "chronic": 0.0, "acwr": np.nan, "series": pd.DataFrame()}
    w = wellness[(wellness["code"].astype(str) == str(code))].copy()
    w["date"] = pd.to_datetime(w["date"].astype(str).str[:10], errors="coerce")
    w["srpe"] = pd.to_numeric(w["srpe"], errors="coerce").fillna(0)
    w = w.dropna(subset=["date"])
    daily = w.groupby("date")["srpe"].sum()
    acute = daily[(daily.index > today - pd.Timedelta(days=7)) & (daily.index <= today)].sum()
    chronic = daily[(daily.index > today - pd.Timedelta(days=28)) & (daily.index <= today)].sum() / 4
    span = (today - daily.index.min()).days if len(daily) else 0
    acwr = acute / chronic if chronic > 0 and span >= 21 else np.nan
    weekly = daily.resample("W").sum().rename("الحمل الأسبوعي (sRPE)").to_frame()
    return {"acute": float(acute), "chronic": float(chronic), "acwr": acwr, "series": weekly}


def video_quality(data, res):
    """يقيّم جودة التصوير: يعيد قائمة (المستوى، الرسالة) والمستوى العام."""
    issues = []
    fps = float(data.get("fps_eff", 30))
    h = float(data.get("height", 0) or 0)
    if res["detection_rate"] < 60:
        issues.append(("red", f"اكتُشف اللاعب في {res['detection_rate']}% فقط من الإطارات. صوّر بإضاءة أفضل وخلفية أوضح."))
    elif res["detection_rate"] < 80:
        issues.append(("amber", f"نسبة اكتشاف اللاعب {res['detection_rate']}%."))
    cam = res.get("camera", {})
    if cam.get("zoomed"):
        issues.append(("red", f"تغيّر التقريب (Zoom) أثناء التصوير ×{cam.get('zoom_ratio')}: السرعات والمسافات لم تُحسب. لا تستخدم التقريب."))
    elif cam.get("panned"):
        issues.append(("amber", "الكاميرا تحركت مع اللاعب. ثبّت الهاتف على حامل."))
    p = res["points"]
    body = np.nanmedian(np.abs(p[:, 0, 1] - np.nanmax(p[:, [27, 28], 1], axis=1))) if len(p) else np.nan
    if h and not np.isnan(body):
        ratio = body / h
        if ratio < 0.12:
            issues.append(("red", f"اللاعب صغير جداً في الصورة ({ratio * 100:.0f}% من ارتفاعها). اقترب أو استخدم دقة أعلى."))
        elif ratio < 0.2:
            issues.append(("amber", f"اللاعب صغير في الصورة ({ratio * 100:.0f}% من ارتفاعها)."))
    real_fps = float(data.get("real_fps", fps))
    if real_fps < 50:
        issues.append(("amber", f"معدل التصوير الفعلي {real_fps:.0f} إطاراً/ث: زمن الارتقاء أقل دقة (±{1000 / real_fps:.0f} ملي ثانية). "
                                "الأفضل 120 أو 240 إطاراً/ث."))
    if res.get("slowmo_applied"):
        issues.append(("amber", f"قُدّر عامل الحركة البطيئة تلقائياً (×{res['slowmo_applied']}). حدده يدوياً للدقة."))
    level = "red" if any(l == "red" for l, _ in issues) else "amber" if issues else "green"
    return level, issues
