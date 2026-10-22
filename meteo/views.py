"""气象数据可视化 Web 视图。"""
import json
from collections import defaultdict
from django.shortcuts import render
from django.conf import settings

from meteo.models import (Station, SurfaceObservation, UpperAirLevel,
                          OceanObservation, RadarProduct, SatelliteImage)


def _downsample_hourly(rows):
    """把 (time, value) 序列按小时聚合(取均值),返回聚合后的序列。"""
    groups = defaultdict(list)
    for t, v in rows:
        groups[t.replace(minute=0, second=0, microsecond=0)].append(v)
    out = []
    for t in sorted(groups):
        vals = [v for v in groups[t] if v is not None]
        if vals:
            out.append((t, round(sum(vals) / len(vals), 2)))
    return out


def _aligned(datasets_dict):
    """{name: [(time, value), ...]} -> {labels, datasets}(共享时间轴,缺失为 null)。"""
    all_times = sorted({t for rows in datasets_dict.values() for t, _ in rows})
    labels = [t.strftime('%m-%d %H:%M') for t in all_times]
    ds = []
    for name, rows in datasets_dict.items():
        m = {t: v for t, v in rows}
        ds.append({'label': name, 'data': [m.get(t) for t in all_times]})
    return {'labels': labels, 'datasets': ds}


def _group(qs, field):
    """把 QuerySet 按站点名聚合为 {name: [(time, value), ...]}。"""
    groups = defaultdict(list)
    for o in qs.order_by('time'):
        groups[o.station.name].append((o.time, getattr(o, field)))
    return dict(groups)


def index(request):
    ctx = {
        'n_surface': SurfaceObservation.objects.count(),
        'n_upper': UpperAirLevel.objects.count(),
        'n_ocean': OceanObservation.objects.count(),
        'n_radar': RadarProduct.objects.count(),
        'n_satellite': SatelliteImage.objects.count(),
        'stations': Station.objects.count(),
    }
    return render(request, 'meteo/index.html', ctx)


def surface(request):
    cn_rows = _group(SurfaceObservation.objects.filter(
        station__station_id__startswith='CN-').select_related('station'), 'temperature_c')
    us_rows = _group(SurfaceObservation.objects.filter(
        station__station_id__istartswith='K').select_related('station'), 'temperature_c')
    cn = _aligned({k: _downsample_hourly(v) for k, v in cn_rows.items()})
    us = _aligned({k: _downsample_hourly(v) for k, v in us_rows.items()})
    stations = list(Station.objects.filter(kind='surface').values(
        'name', 'station_id', 'latitude', 'longitude', 'source'))
    ctx = {
        'cn': json.dumps(cn, ensure_ascii=False),
        'us': json.dumps(us, ensure_ascii=False),
        'stations': stations,
    }
    return render(request, 'meteo/surface.html', ctx)


def upperair(request):
    stations = []
    for st in UpperAirLevel.objects.order_by().values(
            'station', 'station__name', 'station__station_id').distinct():
        sid, name = st['station'], st['station__name']
        sid_str = st['station__station_id']
        latest = UpperAirLevel.objects.filter(station=sid).order_by('-time').first()
        stations.append({
            'sid': sid_str, 'name': name, 'time': latest.time,
            'n_levels': UpperAirLevel.objects.filter(station=sid,
                                                     time=latest.time).count(),
        })
    ctx = {'stations': stations}
    return render(request, 'meteo/upperair.html', ctx)


def ocean(request):
    wave_rows = _group(OceanObservation.objects.select_related('station'),
                       'wave_height_m')
    wave = _aligned({k: _downsample_hourly(v) for k, v in wave_rows.items()})
    buoys = list(Station.objects.filter(kind='ocean').values(
        'name', 'station_id', 'latitude', 'longitude'))
    ctx = {
        'wave': json.dumps(wave, ensure_ascii=False),
        'buoys': buoys,
    }
    return render(request, 'meteo/ocean.html', ctx)


def radar(request):
    items = RadarProduct.objects.order_by('time')
    ctx = {'items': items}
    return render(request, 'meteo/radar.html', ctx)


def satellite(request):
    items = SatelliteImage.objects.order_by('-time')
    ctx = {'items': items,
           'goes': items.filter(satellite__startswith='GOES'),
           'fy': items.filter(satellite__startswith='FY')}
    return render(request, 'meteo/satellite.html', ctx)
