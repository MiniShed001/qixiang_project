"""抓取并入库所有气象数据。

用法: python manage.py ingest_data
"""
import os
import datetime as dt
from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings
from django.utils import timezone

from meteo import fetch
from meteo.models import (Station, SurfaceObservation, UpperAirLevel,
                          OceanObservation, RadarProduct, SatelliteImage)
from meteo import plotting

# 站点元数据
SURFACE_CN = [
    ('北京', 39.90, 116.40), ('上海', 31.23, 121.47), ('广州', 23.13, 113.26),
    ('成都', 30.57, 104.07), ('哈尔滨', 45.80, 126.53),
]
SURFACE_US = [
    ('KDSM', 'Des Moines', 41.53, -93.66), ('KLGA', 'New York', 40.78, -73.87),
    ('KDEN', 'Denver', 39.85, -104.66), ('KMIA', 'Miami', 25.79, -80.29),
    ('KSEA', 'Seattle', 47.45, -122.31),
]
UPPERAIR = [
    ('KOUN', 'Norman OK', 35.22, -97.47), ('KDDC', 'Dodge City KS', 37.76, -99.97),
    ('KABQ', 'Albuquerque NM', 35.04, -106.62), ('KMPX', 'Minneapolis MN', 44.86, -93.57),
]
OCEAN = [
    ('41002', 'South Hatteras', 32.31, -75.36), ('41010', 'Canaveral East', 28.91, -78.49),
    ('46086', 'San Clemente Basin', 32.49, -118.03), ('44065', 'New York Bight', 40.37, -73.70),
    ('51000', 'Northern Hawaii', 23.53, -153.81),
]


class Command(BaseCommand):
    help = '抓取地面/高空/海洋/雷达/卫星数据并入库'

    def handle(self, *args, **opts):
        raw_dir = os.path.join(settings.BASE_DIR, 'data', 'raw')
        os.makedirs(raw_dir, exist_ok=True)

        self._ingest_surface_cn()
        self._ingest_surface_us()
        self._ingest_upperair()
        self._ingest_ocean()
        self._ingest_radar(raw_dir)
        self._ingest_goes(raw_dir)
        self._ingest_fy()
        self.stdout.write(self.style.SUCCESS('全部数据入库完成'))

    # ---------------- 地面(中国) ----------------
    def _ingest_surface_cn(self):
        for name, lat, lon in SURFACE_CN:
            st, _ = Station.objects.update_or_create(
                station_id=f'CN-{name}', defaults=dict(
                    name=name, latitude=lat, longitude=lon,
                    kind='surface', source='Open-Meteo Archive'))
            rows = fetch.fetch_surface_openmeteo(name, lat, lon, days=7)
            SurfaceObservation.objects.filter(station=st).delete()
            objs = [SurfaceObservation(station=st, time=r['time'],
                                       temperature_c=r['temperature_c'],
                                       dewpoint_c=r['dewpoint_c'],
                                       humidity_pct=r['humidity_pct'],
                                       wind_dir_deg=r['wind_dir_deg'],
                                       wind_speed=r['wind_speed'],
                                       pressure_hpa=r['pressure_hpa'],
                                       precip_mm=r['precip_mm']) for r in rows]
            SurfaceObservation.objects.bulk_create(objs)
            self.stdout.write(f'  地面(中国) {name}: {len(objs)} 条')

    # ---------------- 地面(美国) ----------------
    def _ingest_surface_us(self):
        for sid, name, lat, lon in SURFACE_US:
            st, _ = Station.objects.update_or_create(
                station_id=sid, defaults=dict(
                    name=name, latitude=lat, longitude=lon,
                    kind='surface', source='IEM ASOS'))
            rows = fetch.fetch_surface_asos(sid, days=7)
            SurfaceObservation.objects.filter(station=st).delete()
            objs = [SurfaceObservation(station=st, time=r['time'],
                                       temperature_c=r['temperature_c'],
                                       dewpoint_c=r['dewpoint_c'],
                                       humidity_pct=r['humidity_pct'],
                                       wind_dir_deg=r['wind_dir_deg'],
                                       wind_speed=r['wind_speed'],
                                       pressure_hpa=r['pressure_hpa'],
                                       precip_mm=r['precip_mm']) for r in rows]
            SurfaceObservation.objects.bulk_create(objs)
            self.stdout.write(f'  地面(美国) {sid}: {len(objs)} 条')

    # ---------------- 高空 ----------------
    def _ingest_upperair(self):
        for sid, name, lat, lon in UPPERAIR:
            st, _ = Station.objects.update_or_create(
                station_id=sid, defaults=dict(
                    name=name, latitude=lat, longitude=lon,
                    kind='upperair', source='IEM RAOB'))
            rows = fetch.fetch_upperair(sid, days=7)
            if not rows:
                self.stdout.write(self.style.WARNING(f'  高空 {sid}: 无数据(已回退)'))
                continue
            UpperAirLevel.objects.filter(station=st).delete()
            objs = [UpperAirLevel(station=st, time=r['time'],
                                  pressure_hpa=r['pressure_hpa'],
                                  height_m=r['height_m'],
                                  temperature_c=r['temperature_c'],
                                  dewpoint_c=r['dewpoint_c'],
                                  wind_dir_deg=r['wind_dir_deg'],
                                  wind_speed_kt=r['wind_speed_kt']) for r in rows]
            UpperAirLevel.objects.bulk_create(objs)
            # 记录探空次数
            times = len({o.time for o in objs})
            self.stdout.write(f'  高空 {sid}: {len(objs)} 层 / {times} 次探空')

    # ---------------- 海洋 ----------------
    def _ingest_ocean(self):
        for bid, name, lat, lon in OCEAN:
            try:
                rows = fetch.fetch_ocean(bid)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  海洋 {bid}: 抓取失败({e}),跳过'))
                continue
            st, _ = Station.objects.update_or_create(
                station_id=bid, defaults=dict(
                    name=name, latitude=lat, longitude=lon,
                    kind='ocean', source='NOAA NDBC'))
            OceanObservation.objects.filter(station=st).delete()
            objs = [OceanObservation(station=st, time=r['time'],
                                     wind_dir_deg=r['wind_dir_deg'],
                                     wind_speed_ms=r['wind_speed_ms'],
                                     gust_ms=r['gust_ms'],
                                     wave_height_m=r['wave_height_m'],
                                     wave_period_s=r['wave_period_s'],
                                     wave_dir_deg=r['wave_dir_deg'],
                                     pressure_hpa=r['pressure_hpa'],
                                     air_temp_c=r['air_temp_c'],
                                     water_temp_c=r['water_temp_c'],
                                     dewpoint_c=r['dewpoint_c']) for r in rows]
            OceanObservation.objects.bulk_create(objs)
            self.stdout.write(f'  海洋 {bid} ({name}): {len(objs)} 条')

    # ---------------- 雷达 ----------------
    def _ingest_radar(self, raw_dir):
        items = fetch.fetch_radar_composite(raw_dir, n_steps=8, step_min=30)
        RadarProduct.objects.all().delete()
        for it in items:
            with open(it['path'], 'rb') as f:
                rp = RadarProduct(time=it['time'], product=it['product'],
                                  region=it['region'], source_url=it['url'])
                rp.image.save(os.path.basename(it['path']), File(f), save=True)
        self.stdout.write(f'  雷达: {len(items)} 张拼图')

    # ---------------- GOES ----------------
    def _ingest_goes(self, raw_dir):
        items = fetch.fetch_goes_cmi(raw_dir, n_steps=5)
        got = 0
        for it in items:
            png = os.path.join(raw_dir, os.path.basename(it['path']) + '.png')
            try:
                plotting.render_goes_ir(it['path'], png, channel=it['channel'])
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  GOES 渲染失败: {e}'))
                continue
            with open(png, 'rb') as f:
                si = SatelliteImage(satellite=it['satellite'],
                                    channel=it['channel'], time=it['time'],
                                    source_url=it['url'], note=it['note'])
                si.image.save(os.path.basename(png), File(f), save=True)
            got += 1
        self.stdout.write(f'  卫星 GOES-16: {got} 张云图')

    # ---------------- 风云 ----------------
    def _ingest_fy(self):
        info = fetch.fetch_fy4()
        self.stdout.write(self.style.WARNING(
            f'  风云卫星: {info["reason"]} 注册地址 {info["register_url"]}'))
