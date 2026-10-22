"""气象数据获取与解析模块。

所有数据源均为免费公开、无需 API key 的真实数据:
- 地面(中国):Open-Meteo 历史档案
- 地面(美国):IEM ASOS
- 高空:IEM 探空档案(站点用 K 前缀,如 KOUN)
- 海洋:NOAA NDBC 浮标
- 雷达:IEM 全国雷达拼图
- 卫星:GOES-16/18(AWS 开放桶,netCDF)
- 风云卫星:NSMC 需实名注册,见 fetch_fy() 说明
"""
import datetime as dt
import io
import os
import re
import time
import requests
import xml.etree.ElementTree as ET

UA = {'User-Agent': 'meteo-viz/1.0 (research, local)'}
S3 = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}
MISSING = {'M', 'MM', 'null', ''}

GOES_BUCKET = 'https://noaa-goes16.s3.amazonaws.com'
RADAR_BASE = 'https://mesonet.agron.iastate.edu/archive/data'


def _get(url, params=None, timeout=90, retries=3):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.ReadTimeout) as e:
            last = e
            time.sleep(2 ** i)
    raise last


def _f(v):
    """M / MM 缺失值 -> None,否则 float。"""
    if v is None:
        return None
    s = str(v).strip()
    if s in MISSING:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _s3_list(prefix, max_keys=1000, delimiter=None):
    """列出 S3 桶某前缀下的对象 key(或 delimiter 模式下的公共前缀)。"""
    url = f'{GOES_BUCKET}/?prefix={prefix}&max-keys={max_keys}'
    if delimiter:
        url += f'&delimiter={delimiter}'
    r = _get(url)
    root = ET.fromstring(r.content)
    out = []
    if delimiter:
        for c in root.findall('s3:CommonPrefixes', S3):
            p = c.find('s3:Prefix', S3)
            if p is not None and p.text:
                out.append(p.text)
    else:
        for c in root.findall('s3:Contents', S3):
            k = c.find('s3:Key', S3)
            if k is not None and k.text:
                out.append(k.text)
    return out


# ---------------------------------------------------------------------------
# 地面气象
# ---------------------------------------------------------------------------
def fetch_surface_openmeteo(city, lat, lon, days=7):
    """Open-Meteo 历史档案,逐小时地面要素(中国城市)。"""
    now = dt.datetime.now(dt.timezone.utc)
    end = now - dt.timedelta(days=1)
    start = end - dt.timedelta(days=days - 1)
    params = {
        'latitude': lat, 'longitude': lon,
        'start_date': start.strftime('%Y-%m-%d'),
        'end_date': end.strftime('%Y-%m-%d'),
        'hourly': 'temperature_2m,relative_humidity_2m,dew_point_2m,'
                  'surface_pressure,wind_speed_10m,wind_direction_10m,precipitation',
        'timezone': 'UTC',
    }
    r = _get('https://archive-api.open-meteo.com/v1/archive', params=params)
    d = r.json()['hourly']
    rows = []
    for i, t in enumerate(d['time']):
        rows.append({
            'time': dt.datetime.fromisoformat(t).replace(tzinfo=dt.timezone.utc),
            'temperature_c': d['temperature_2m'][i],
            'humidity_pct': d['relative_humidity_2m'][i],
            'dewpoint_c': d['dew_point_2m'][i],
            'pressure_hpa': d['surface_pressure'][i],
            # Open-Meteo 风速单位 km/h -> m/s
            'wind_speed': round(d['wind_speed_10m'][i] / 3.6, 2) if d['wind_speed_10m'][i] is not None else None,
            'wind_dir_deg': d['wind_direction_10m'][i],
            'precip_mm': d['precipitation'][i],
        })
    return rows


def fetch_surface_asos(station, days=7):
    """IEM ASOS 美国地面站,逐小时(UTC)。"""
    now = dt.datetime.now(dt.timezone.utc)
    end = now - dt.timedelta(days=1)
    start = end - dt.timedelta(days=days - 1)
    params = {
        'station': station,
        'data': 'tmpf,dwpf,relh,drct,sknt,mslp,p01i',
        'year1': start.year, 'month1': start.month, 'day1': start.day,
        'year2': end.year, 'month2': end.month, 'day2': end.day,
        'tz': 'Etc/UTC', 'format': 'onlycomma',
    }
    r = _get('https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py', params=params)
    lines = r.text.strip().splitlines()
    if len(lines) < 2:
        return []
    header = lines[0].split(',')
    idx = {h: i for i, h in enumerate(header)}
    rows = []
    for ln in lines[1:]:
        p = ln.split(',')
        if len(p) < len(header):
            continue
        tmpf = _f(p[idx['tmpf']]); dwpf = _f(p[idx['dwpf']]); sknt = _f(p[idx['sknt']])
        p01i = _f(p[idx['p01i']])
        rows.append({
            'time': dt.datetime.fromisoformat(p[idx['valid']]).replace(tzinfo=dt.timezone.utc),
            'temperature_c': round((tmpf - 32) * 5 / 9, 1) if tmpf is not None else None,
            'dewpoint_c': round((dwpf - 32) * 5 / 9, 1) if dwpf is not None else None,
            'humidity_pct': _f(p[idx['relh']]),
            'wind_dir_deg': _f(p[idx['drct']]),
            'wind_speed': round(sknt * 0.514444, 2) if sknt is not None else None,  # kt->m/s
            'pressure_hpa': _f(p[idx['mslp']]),
            'precip_mm': round(p01i * 25.4, 2) if p01i is not None else None,  # in->mm
        })
    return rows


# ---------------------------------------------------------------------------
# 高空气象
# ---------------------------------------------------------------------------
def fetch_upperair(station, days=7, fallback=('2024', '8', '1')):
    """IEM 探空档案,返回各气压层记录。station 用 K 前缀(如 KOUN)。

    若近期无数据,回退到已知有数据的历史日期。
    """
    now = dt.datetime.now(dt.timezone.utc)
    end = now - dt.timedelta(days=1)
    start = end - dt.timedelta(days=days - 1)
    for (y1, m1, d1, y2, m2, d2) in [
        (start.year, start.month, start.day, end.year, end.month, end.day),
        (fallback[0], fallback[1], fallback[2], fallback[0], fallback[1], fallback[2]),
    ]:
        sts = f'{y1:04d}-{m1:02d}-{d1:02d}T00:00'
        ets = f'{y2:04d}-{m2:02d}-{d2:02d}T23:59'
        params = {'station': station, 'sts': sts, 'ets': ets, 'format': 'onlycomma'}
        r = _get('https://mesonet.agron.iastate.edu/cgi-bin/request/raob.py', params=params)
        lines = r.text.strip().splitlines()
        if len(lines) < 2:
            continue
        header = lines[0].split(',')
        idx = {h: i for i, h in enumerate(header)}
        rows = []
        for ln in lines[1:]:
            p = ln.split(',')
            if len(p) < len(header):
                continue
            rows.append({
                'time': dt.datetime.fromisoformat(p[idx['validUTC']]).replace(tzinfo=dt.timezone.utc),
                'pressure_hpa': _f(p[idx['pressure_mb']]),
                'height_m': _f(p[idx['height_m']]),
                'temperature_c': _f(p[idx['tmpc']]),
                'dewpoint_c': _f(p[idx['dwpc']]),
                'wind_dir_deg': _f(p[idx['drct']]),
                'wind_speed_kt': _f(p[idx['speed_kts']]),
            })
        if rows:
            return rows
    return []


# ---------------------------------------------------------------------------
# 海洋气象
# ---------------------------------------------------------------------------
NDBC_FIELDS = ['WDIR', 'WSPD', 'GST', 'WVHT', 'DPD', 'APD', 'MWD',
               'PRES', 'ATMP', 'WTMP', 'DEWP', 'VIS', 'PTDY', 'TIDE']


def fetch_ocean(buoy_id):
    """NOAA NDBC 实时浮标数据(近 45 天)。"""
    r = _get(f'https://www.ndbc.noaa.gov/data/realtime2/{buoy_id}.txt')
    rows = []
    for ln in r.text.splitlines():
        if not ln or ln.startswith('#'):
            continue
        p = ln.split()
        if len(p) < 5:
            continue
        # YY MM DD hh mm 之后是要素
        y, mo, d, h, mi = int(p[0]), int(p[1]), int(p[2]), int(p[3]), int(p[4])
        t = dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone.utc)
        vals = p[5:5 + len(NDBC_FIELDS)]
        rec = {'time': t}
        rec['wind_dir_deg'] = _f(vals[0])
        rec['wind_speed_ms'] = _f(vals[1])
        rec['gust_ms'] = _f(vals[2])
        rec['wave_height_m'] = _f(vals[3])
        rec['wave_period_s'] = _f(vals[4]) if vals[4] not in MISSING else _f(vals[5])
        rec['wave_dir_deg'] = _f(vals[6])
        rec['pressure_hpa'] = _f(vals[7])
        rec['air_temp_c'] = _f(vals[8])
        rec['water_temp_c'] = _f(vals[9])
        rec['dewpoint_c'] = _f(vals[10])
        rows.append(rec)
    return rows


# ---------------------------------------------------------------------------
# 天气雷达
# ---------------------------------------------------------------------------
def fetch_radar_composite(raw_dir, n_steps=8, step_min=30):
    """下载 IEM 美国全国雷达拼图(base reflectivity, n0q)。"""
    os.makedirs(raw_dir, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    # 拼图约 5 分钟一档,取最近的整 10 分钟时次
    base = now.replace(minute=(now.minute // 10) * 10, second=0, microsecond=0)
    out = []
    for i in range(n_steps):
        t = base - dt.timedelta(minutes=i * step_min)
        url = (f'{RADAR_BASE}/{t:%Y/%m/%d}/GIS/uscomp/'
               f'n0q_{t:%Y%m%d%H%M}.png')
        fn = os.path.join(raw_dir, f'radar_n0q_{t:%Y%m%d%H%M}.png')
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code != 200:
                continue
            with open(fn, 'wb') as f:
                f.write(r.content)
            out.append({'time': t, 'path': fn, 'url': url,
                        'product': 'n0q', 'region': 'uscomp'})
        except requests.RequestException:
            continue
    return out


# ---------------------------------------------------------------------------
# 国外气象卫星 GOES
# ---------------------------------------------------------------------------
def _goes_latest_year_doy():
    """找到 GOES 桶 CMIPC 最近可用年份与日序。"""
    for year in ('2025', '2024', '2023'):
        prefixes = _s3_list(f'ABI-L2-CMIPC/{year}/', max_keys=1000, delimiter='/')
        doys = []
        for p in prefixes:
            m = re.search(rf'/{year}/(\d+)/$', p)
            if m:
                doys.append(int(m.group(1)))
        if doys:
            return year, max(doys)
    return None, None


def fetch_goes_cmi(raw_dir, n_steps=5, channels=('C13',)):
    """下载 GOES-16 CONUS 云图 netCDF(C13 红外为主)。"""
    os.makedirs(raw_dir, exist_ok=True)
    year, doy = _goes_latest_year_doy()
    if not year:
        return []
    # 该日的小时目录
    hour_prefs = _s3_list(f'ABI-L2-CMIPC/{year}/{doy:03d}/', max_keys=500, delimiter='/')
    hours = []
    for h in hour_prefs:
        m = re.search(rf'/{doy:03d}/(\d+)/$', h)
        if m:
            hours.append(int(m.group(1)))
    hours.sort()
    if not hours:
        return []
    # 均匀选取若干小时,每取一个 C13 文件
    step = max(1, len(hours) // n_steps)
    picked = hours[::step][:n_steps]
    out = []
    for hh in picked:
        keys = _s3_list(f'ABI-L2-CMIPC/{year}/{doy:03d}/{hh:02d}/', max_keys=500)
        c13 = [k for k in keys if 'M6C13_G16_' in k]
        if not c13:
            continue
        key = c13[len(c13) // 2]  # 取该小时中间一档
        fn = os.path.join(raw_dir, os.path.basename(key))
        url = f'{GOES_BUCKET}/{key}'
        try:
            r = requests.get(url, headers=UA, timeout=300)
            if r.status_code != 200:
                continue
            with open(fn, 'wb') as f:
                f.write(r.content)
            m = re.search(r'_s(\d{14})_', key)
            t = (dt.datetime.strptime(m.group(1), '%Y%j%H%M%S%f')
                 .replace(tzinfo=dt.timezone.utc)) if m else None
            out.append({'time': t, 'path': fn, 'url': url,
                        'satellite': 'GOES-16', 'channel': 'C13',
                        'note': 'ABI 红外通道 10.3µm (CONUS)'})
        except requests.RequestException:
            continue
    return out


# ---------------------------------------------------------------------------
# 风云卫星(需实名注册,此处提供凭证就绪的下载管线骨架)
# ---------------------------------------------------------------------------
def fetch_fy4(account=None):
    """风云四号 L1 数据下载管线。

    NSMC(国家卫星气象中心)数据服务网要求实名注册:
    https://satellite.nsmc.org.cn 实名认证后登录,通过订单方式下载 FY-4A/4B
    AGRI L1 数据(HDF5 格式,含 14 通道)。数据格式与解析方式见
    https://github.com/zxdawn/FY-4 (satpy 的 agri_l1 reader)。

    传入 account = {'user': ..., 'pass': ...} 后可扩展为:
      1. 登录获取会话 cookie
      2. 按 卫星/仪器/产品/时间 检索,提交订单
      3. 轮询订单状态,下载文件列表中的 HDF5 文件
      4. 用 satpy Scene(reader='agri_l1')读取通道,渲染云图
    因需实名审核(约 1 个工作日),本系统默认以公开替代源演示,风云管线留待
    用户完成注册后一键启用。
    """
    return {
        'available': False,
        'reason': 'NSMC 要求实名注册并通过审核后,才能下载 FY-4 数据。',
        'register_url': 'https://satellite.nsmc.org.cn',
        'format_doc': 'https://github.com/zxdawn/FY-4',
    }
