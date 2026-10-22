"""从数据库生成全部可视化产物(静态图 + GIF 动画)。

用法: python manage.py make_visuals
"""
import os
import numpy as np
from django.core.management.base import BaseCommand
from django.conf import settings

from meteo.models import (Station, SurfaceObservation, UpperAirLevel,
                          OceanObservation, RadarProduct, SatelliteImage)
from meteo import plotting

APP_STATIC = os.path.join(settings.BASE_DIR, 'meteo', 'static', 'meteo')
PLOTS = os.path.join(APP_STATIC, 'plots')
IMG = os.path.join(APP_STATIC, 'img')


def _series(obs_qs, field):
    """把 QuerySet 聚合成 {站点名: (times[], values[])}"""
    out = {}
    for o in obs_qs.order_by('time'):
        out.setdefault(o.station.name, ([], []))
        out[o.station.name][0].append(o.time)
        out[o.station.name][1].append(getattr(o, field))
    return out


class Command(BaseCommand):
    help = '生成全部可视化图表与动画'

    def handle(self, *args, **opts):
        os.makedirs(PLOTS, exist_ok=True)
        os.makedirs(IMG, exist_ok=True)
        self._surface()
        self._upperair()
        self._maps()
        self._ocean()
        self._radar_gif()
        self._goes_gif()
        self.stdout.write(self.style.SUCCESS('可视化生成完成'))

    def _surface(self):
        # 中国地面温度时序
        cn = _series(SurfaceObservation.objects.filter(station__kind='surface',
                     station__station_id__startswith='CN-').select_related('station'),
                     'temperature_c')
        if cn:
            plotting.plot_surface_ts(cn, os.path.join(PLOTS, 'surface_temp_cn.png'),
                                     'temperature_c', 'Temperature (°C)',
                                     'Surface Temperature — China (hourly)')
            plotting.plot_surface_ts(cn, os.path.join(PLOTS, 'surface_pressure_cn.png'),
                                     'pressure_hpa', 'Pressure (hPa)',
                                     'Surface Pressure — China (hourly)')
        # 美国地面温度时序
        us = _series(SurfaceObservation.objects.filter(station__kind='surface',
                     station__station_id__istartswith='K').select_related('station'),
                     'temperature_c')
        if us:
            plotting.plot_surface_ts(us, os.path.join(PLOTS, 'surface_temp_us.png'),
                                     'temperature_c', 'Temperature (°C)',
                                     'Surface Temperature — USA (hourly)')
        # 风玫瑰(取一个美国站)
        st = SurfaceObservation.objects.filter(station__kind='surface',
             station__station_id__istartswith='K', wind_speed__isnull=False,
             wind_dir_deg__isnull=False).first()
        if st:
            obs = SurfaceObservation.objects.filter(station=st.station,
                    wind_speed__isnull=False, wind_dir_deg__isnull=False)
            dirs = [o.wind_dir_deg for o in obs]
            spds = [o.wind_speed for o in obs]
            if len(dirs) > 5:
                plotting.plot_wind_rose(dirs, spds,
                    os.path.join(PLOTS, 'wind_rose.png'),
                    f'Wind Rose — {st.station.name}')
        self.stdout.write(f'  地面图表完成')

    def _upperair(self):
        for st in UpperAirLevel.objects.order_by().values(
                'station', 'station__name', 'station__station_id').distinct():
            sid = st['station']
            name = st['station__name']
            sid_str = st['station__station_id']
            latest = (UpperAirLevel.objects.filter(station=sid)
                      .order_by('-time').values('time').first())
            if not latest:
                continue
            t = latest['time']
            levels = (UpperAirLevel.objects.filter(station=sid, time=t)
                      .order_by('-pressure_hpa'))
            p = [l.pressure_hpa for l in levels]
            T = [l.temperature_c if l.temperature_c is not None else np.nan for l in levels]
            Td = [l.dewpoint_c if l.dewpoint_c is not None else np.nan for l in levels]
            wd = [l.wind_dir_deg for l in levels]
            ws = [l.wind_speed_kt for l in levels]
            if len(p) < 5:
                continue
            plotting.plot_skewt(p, T, Td, wd, ws,
                                os.path.join(PLOTS, f'skewt_{sid_str}.png'),
                                f'Skew-T — {name} {t:%Y-%m-%d %H:%M}Z')
            plotting.plot_upper_profile(p, T, Td, None,
                                os.path.join(PLOTS, f'profile_{sid_str}.png'),
                                f'Vertical Profile — {name}')
            self.stdout.write(f'  高空 {name}: Skew-T + 廓线')

    def _maps(self):
        """静态站点/浮标分布地图(无需 JS)。"""
        coast = os.path.join(APP_STATIC, 'vendor', 'ne_110m_coastline.geojson')
        surf = []
        for s in Station.objects.filter(kind='surface'):
            color = '#d94f30' if s.station_id.startswith('CN-') else '#0b6bcb'
            surf.append((s.name, s.latitude, s.longitude, color))
        if surf:
            plotting.plot_station_map(surf, os.path.join(PLOTS, 'surface_map.png'),
                                      'Surface Stations', coast)
        ocean = [(s.name, s.latitude, s.longitude, '#d94f30')
                 for s in Station.objects.filter(kind='ocean')]
        if ocean:
            plotting.plot_station_map(ocean, os.path.join(PLOTS, 'ocean_map.png'),
                                      'NDBC Buoys', coast)
        self.stdout.write('  站点地图完成')

    def _ocean(self):
        wave = _series(OceanObservation.objects.select_related('station'), 'wave_height_m')
        sst = _series(OceanObservation.objects.select_related('station'), 'water_temp_c')
        if wave:
            plotting.plot_ocean_ts(wave, os.path.join(PLOTS, 'ocean_wave.png'),
                                   'wave_height_m', 'Wave Height (m)',
                                   'Significant Wave Height — NDBC Buoys')
            # 波高演变动画(取第一个浮标)
            first = {next(iter(wave)): wave[next(iter(wave))]}
            plotting.ocean_evolution_anim(first, os.path.join(IMG, 'ocean_wave_anim.gif'))
        if sst:
            plotting.plot_ocean_ts(sst, os.path.join(PLOTS, 'ocean_sst.png'),
                                   'water_temp_c', 'Sea Surface Temp (°C)',
                                   'Sea Surface Temperature — NDBC Buoys')
        # 风速-波高散点
        o = OceanObservation.objects.filter(wind_speed_ms__isnull=False,
                                            wave_height_m__isnull=False)
        if o.count() > 10:
            plotting.plot_ocean_scatter([x.wind_speed_ms for x in o],
                                        [x.wave_height_m for x in o],
                                        os.path.join(PLOTS, 'ocean_scatter.png'))
        self.stdout.write('  海洋图表完成')

    def _radar_gif(self):
        items = list(RadarProduct.objects.order_by('time'))
        if items:
            paths = [r.image.path for r in items]
            plotting.images_to_gif(paths, os.path.join(IMG, 'radar_loop.gif'),
                                   duration_ms=500)
            self.stdout.write(f'  雷达动画: {len(items)} 帧')

    def _goes_gif(self):
        items = list(SatelliteImage.objects.filter(satellite__startswith='GOES')
                     .order_by('time'))
        if items:
            paths = [r.image.path for r in items]
            plotting.images_to_gif(paths, os.path.join(IMG, 'goes_loop.gif'),
                                   duration_ms=500)
            self.stdout.write(f'  GOES 动画: {len(items)} 帧')
