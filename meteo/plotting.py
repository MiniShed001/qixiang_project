"""气象数据可视化模块。

产出物:
- 静态图(matplotlib PNG):地面时序、风玫瑰、Skew-T、廓线、海洋时序/散点
- 卫星云图渲染(GOES netCDF -> PNG)
- GIF 动画:雷达回波演变、卫星云图演变、海洋波高演变
所有 matplotlib 图用英文标注(避免字体缺失),网页界面用中文。
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import numpy as np
from PIL import Image

# 注册中文字体,避免站点名(北京/上海等)显示为方块
for _f in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
           '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc']:
    if os.path.exists(_f):
        try:
            fm.fontManager.addfont(_f)
        except Exception:
            pass
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK SC', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

plt.rcParams['figure.dpi'] = 110
plt.rcParams['savefig.bbox'] = 'tight'


# ---------------------------------------------------------------------------
# 地面气象
# ---------------------------------------------------------------------------
def plot_surface_ts(series, out_path, field='temperature_c',
                    ylabel='Temperature (°C)', title='Surface Temperature'):
    """多条站点时序曲线。series: {station_name: (times[], values[])}"""
    fig, ax = plt.subplots(figsize=(10, 5))
    for name, (t, v) in series.items():
        ax.plot(t, v, label=name, linewidth=1.6)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H'))
    ax.set_xlabel('Time (UTC)')
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(ncol=2, fontsize=8, loc='best')
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.savefig(out_path)
    plt.close(fig)


def plot_wind_rose(directions, speeds, out_path, title='Wind Rose'):
    """风玫瑰图(按 16 方位统计风速分布)。"""
    directions = np.asarray(directions, dtype=float)
    speeds = np.asarray(speeds, dtype=float)
    fig = plt.figure(figsize=(6, 6))
    ax = fig.add_subplot(111, projection='polar')
    bins_dir = np.arange(-np.pi / 16, 2 * np.pi, np.pi / 8)  # 16 方位
    dir_rad = np.deg2rad(directions)
    # 风速分档
    speed_bins = [0, 2, 5, 10, 20, 100]
    labels = ['0-2', '2-5', '5-10', '10-20', '>20 m/s']
    colors = ['#8fd0ff', '#3fa7f0', '#1f77b4', '#0a4d8c', '#062a52']
    bottom = np.zeros(16)
    for i in range(len(speed_bins) - 1):
        mask = (speeds >= speed_bins[i]) & (speeds < speed_bins[i + 1])
        hist, _ = np.histogram(dir_rad[mask], bins=bins_dir)
        hist = hist / max(1, len(speeds)) * 100
        ax.bar(bins_dir[:-1], hist, width=np.pi / 8, bottom=bottom,
               color=colors[i], edgecolor='white', linewidth=0.4, label=labels[i])
        bottom += hist
    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)
    ax.set_title(title, pad=20)
    ax.legend(loc='lower left', bbox_to_anchor=(1.05, 0.0), fontsize=7)
    fig.savefig(out_path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 高空气象
# ---------------------------------------------------------------------------
SKEW = 35.0


def _tx(T, p):
    """Skew-T 温度横坐标变换。"""
    return T + SKEW * np.log(1000.0 / p)


def plot_skewt(pressure, temp, dewpoint, wind_dir=None, wind_speed=None,
               out_path='skewt.png', title='Skew-T / Log-P'):
    """标准 Skew-T log-P 斜温图。"""
    p = np.array(pressure, dtype=float)
    T = np.array(temp, dtype=float)
    Td = np.array(dewpoint, dtype=float)

    fig, ax = plt.subplots(figsize=(7.5, 9))
    ax.set_yscale('log')
    ax.invert_yaxis()
    ax.set_ylim(max(p), min(p))
    ax.set_xlim(-50, 50)

    # --- 等温线(斜线) ---
    p_grid = np.linspace(1050, 100, 200)
    for t0 in range(-100, 55, 5):
        ax.plot(_tx(t0, p_grid), p_grid, color='#e0e0e0', linewidth=0.7, zorder=1)
    # --- 干绝热线(位温) ---
    for theta in range(-40, 160, 10):
        tline = theta * (p_grid / 1000.0) ** 0.286
        ax.plot(_tx(tline, p_grid), p_grid, color='#f5d5a0', linewidth=0.6, zorder=1)
    # --- 饱和混合比线(虚线) ---
    for ws in [0.1, 0.2, 0.4, 0.8, 1.5, 3, 6, 12, 20]:
        es = ws * p_grid / (0.622 + ws)
        es = np.clip(es, 1e-3, None)
        tline = 243.5 * np.log(es / 6.112) / (17.67 - np.log(es / 6.112))
        ax.plot(_tx(tline, p_grid), p_grid, color='#c0e0c0', linewidth=0.6,
                linestyle='--', zorder=1)

    # --- 实际廓线 ---
    ax.plot(_tx(T, p), p, color='red', linewidth=2, zorder=3, label='Temperature')
    ax.plot(_tx(Td, p), p, color='green', linewidth=2, zorder=3, label='Dewpoint')

    # --- 风羽 ---
    if wind_dir is not None and wind_speed is not None:
        wd = np.asarray(wind_dir, dtype=float)
        ws = np.asarray(wind_speed, dtype=float)
        u = -np.sin(np.deg2rad(wd)) * ws
        v = -np.cos(np.deg2rad(wd)) * ws
        ax.barbs(np.full_like(p, 42.0), p, u, v, length=5.5, zorder=4, color='navy')

    # --- 坐标标签 ---
    ax.set_yticks([1000, 850, 700, 500, 300, 200, 100])
    ax.set_yticklabels(['1000', '850', '700', '500', '300', '200', '100'])
    ax.set_ylabel('Pressure (hPa)')
    ax.set_xticks(range(-40, 45, 10))
    ax.set_xlabel('Temperature (°C)')
    ax.set_title(title)
    ax.legend(loc='lower left', fontsize=9)
    ax.grid(False)
    fig.savefig(out_path)
    plt.close(fig)


def plot_upper_profile(pressure, temp, dewpoint, height=None, out_path='profile.png',
                       title='Vertical Profile'):
    """温度/露点随气压(或高度)的垂直廓线。"""
    p = np.array(pressure, dtype=float)
    T = np.array(temp, dtype=float)
    Td = np.array(dewpoint, dtype=float)
    fig, ax = plt.subplots(figsize=(6, 8))
    ax.plot(T, p, 'r-o', markersize=4, label='Temperature')
    ax.plot(Td, p, 'g-s', markersize=4, label='Dewpoint')
    ax.set_yscale('log')
    ax.invert_yaxis()
    ax.set_yticks([1000, 850, 700, 500, 300, 200, 100])
    ax.set_yticklabels(['1000', '850', '700', '500', '300', '200', '100'])
    ax.set_ylabel('Pressure (hPa)')
    ax.set_xlabel('Temperature (°C)')
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.savefig(out_path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 海洋气象
# ---------------------------------------------------------------------------
def plot_ocean_ts(series, out_path, field='wave_height_m',
                  ylabel='Wave Height (m)', title='Significant Wave Height'):
    """浮标时序。series: {name: (times[], values[])}"""
    return plot_surface_ts(series, out_path, field, ylabel, title)


def plot_ocean_scatter(wind, wave, out_path, title='Wind Speed vs Wave Height'):
    """风速-波高散点 + 线性拟合。"""
    fig, ax = plt.subplots(figsize=(7, 5))
    w = np.array(wind, dtype=float)
    h = np.array(wave, dtype=float)
    m = np.isfinite(w) & np.isfinite(h)
    w, h = w[m], h[m]
    ax.scatter(w, h, s=14, alpha=0.55, color='#1f77b4')
    if len(w) > 2:
        k, b = np.polyfit(w, h, 1)
        ax.plot(np.sort(w), k * np.sort(w) + b, 'r--', linewidth=1.6,
                label=f'trend: {k:.3f}')
    ax.set_xlabel('Wind Speed (m/s)')
    ax.set_ylabel('Wave Height (m)')
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.savefig(out_path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 静态世界地图(海岸线 + 站点)
# ---------------------------------------------------------------------------
def plot_station_map(stations, out_path, title='Stations', coast_path=None):
    """等距圆柱投影世界地图:海岸线 + 站点标记。stations: [(name, lat, lon, color)]"""
    import json as _json
    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.set_facecolor('#eaf4fb')
    if coast_path and os.path.exists(coast_path):
        with open(coast_path, encoding='utf-8') as f:
            geo = _json.load(f)
        for feat in geo.get('features', []):
            g = feat.get('geometry', {})
            if g.get('type') == 'LineString':
                lines = [g['coordinates']]
            elif g.get('type') == 'MultiLineString':
                lines = g['coordinates']
            else:
                continue
            for line in lines:
                xs = [c[0] for c in line]
                ys = [c[1] for c in line]
                ax.plot(xs, ys, color='#9aa5b1', linewidth=0.6, zorder=1)
    for name, lat, lon, color in stations:
        ax.plot(lon, lat, 'o', color=color, markersize=7, zorder=3,
                markeredgecolor='white', markeredgewidth=0.8)
        ax.annotate(name, (lon, lat), textcoords='offset points', xytext=(0, 6),
                    fontsize=7, ha='center', zorder=4)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 88)
    ax.set_aspect('equal')
    ax.set_xticks(range(-180, 181, 60))
    ax.set_yticks(range(-60, 91, 30))
    ax.grid(alpha=0.2, linewidth=0.4)
    ax.set_title(title)
    fig.savefig(out_path, bbox_inches='tight')
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# 卫星云图渲染
# ---------------------------------------------------------------------------
def render_goes_ir(nc_path, out_png, vmin=190, vmax=320, channel='C13'):
    """GOES ABI 红外通道 netCDF -> 灰度 PNG(冷云亮白)。"""
    import xarray as xr
    ds = xr.open_dataset(nc_path)
    var = 'CMI' if 'CMI' in ds else list(ds.data_vars)[0]
    data = ds[var].values.astype(float)
    ds.close()
    # 填充值/无效值掩膜
    data = np.where(np.isfinite(data), data, np.nan)
    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(data, cmap='gray_r', vmin=vmin, vmax=vmax, interpolation='nearest')
    ax.set_title(f'GOES-16 ABI {channel} Brightness Temperature')
    ax.axis('off')
    fig.colorbar(im, ax=ax, fraction=0.03, label='Brightness Temp (K)')
    fig.savefig(out_png, bbox_inches='tight')
    plt.close(fig)
    return out_png


# ---------------------------------------------------------------------------
# GIF 动画
# ---------------------------------------------------------------------------
def images_to_gif(image_paths, out_gif, duration_ms=600, label=''):
    """把若干图像帧合成 GIF。"""
    frames = []
    for p in image_paths:
        if os.path.exists(p):
            im = Image.open(p).convert('RGB')
            im.thumbnail((900, 900))
            frames.append(im)
    if not frames:
        return None
    frames[0].save(out_gif, save_all=True, append_images=frames[1:],
                   duration=duration_ms, loop=0)
    return out_gif


def ocean_evolution_anim(series, out_gif, field='wave_height_m',
                         ylabel='Wave Height (m)', title='Wave Height Evolution',
                         max_frames=48):
    """波高随时间的增长动画(单浮标),下采样到 max_frames 帧。"""
    name, (t, v) = next(iter(series.items()))
    t = np.array(t, dtype='datetime64[s]')
    v = np.array(v, dtype=float)
    m = np.isfinite(v)
    t, v = t[m], v[m]
    if len(t) > max_frames:
        idx = np.linspace(0, len(t) - 1, max_frames).astype(int)
        t, v = t[idx], v[idx]
    if len(t) < 3:
        return None
    fig, ax = plt.subplots(figsize=(7, 4))
    frames = []
    for i in range(1, len(t) + 1):
        ax.clear()
        ax.plot(t[:i], v[:i], '-o', markersize=3, color='#1f77b4')
        ax.set_xlim(t[0], t[-1])
        vmin, vmax = np.nanmin(v), np.nanmax(v)
        pad = max(0.2, (vmax - vmin) * 0.1)
        ax.set_ylim(vmin - pad, vmax + pad)
        ax.set_ylabel(ylabel)
        ax.set_title(f'{title} — {name}')
        ax.grid(alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H'))
        fig.autofmt_xdate()
        fig.canvas.draw()
        buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
        frames.append(Image.fromarray(buf))
    plt.close(fig)
    if frames:
        frames[0].save(out_gif, save_all=True, append_images=frames[1:],
                       duration=300, loop=0)
        return out_gif
    return None
