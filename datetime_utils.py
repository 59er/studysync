from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def utc_now():
    return datetime.now(timezone.utc)

def str_to_utc_datetime(date_str, format='%Y-%m-%d'):
    try:
        return datetime.strptime(date_str, format).replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise ValueError(f"Invalid date string format: {e}")

def utc_to_jst(utc_dt):
    if utc_dt.tzinfo is None or utc_dt.tzinfo.utcoffset(utc_dt) is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(ZoneInfo("Asia/Tokyo"))

def register_jinja_filters(app):
    @app.template_filter('utc_to_jst')
    def utc_to_jst_filter(dt):
        if dt is None:
            return None
        return utc_to_jst(dt)