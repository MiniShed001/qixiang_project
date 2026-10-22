from django.contrib import admin
from .models import (Station, SurfaceObservation, UpperAirLevel,
                     OceanObservation, RadarProduct, SatelliteImage)


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ('station_id', 'name', 'kind', 'latitude', 'longitude', 'source')
    list_filter = ('kind',)
    search_fields = ('station_id', 'name')


@admin.register(SurfaceObservation)
class SurfaceObservationAdmin(admin.ModelAdmin):
    list_display = ('station', 'time', 'temperature_c', 'pressure_hpa',
                    'wind_speed', 'precip_mm')
    list_filter = ('station',)


@admin.register(UpperAirLevel)
class UpperAirLevelAdmin(admin.ModelAdmin):
    list_display = ('station', 'time', 'pressure_hpa', 'height_m',
                    'temperature_c', 'wind_speed_kt')


@admin.register(OceanObservation)
class OceanObservationAdmin(admin.ModelAdmin):
    list_display = ('station', 'time', 'wave_height_m', 'water_temp_c',
                    'pressure_hpa', 'wind_speed_ms')


@admin.register(RadarProduct)
class RadarProductAdmin(admin.ModelAdmin):
    list_display = ('time', 'product', 'region', 'image')


@admin.register(SatelliteImage)
class SatelliteImageAdmin(admin.ModelAdmin):
    list_display = ('satellite', 'channel', 'time', 'image', 'note')
    list_filter = ('satellite', 'channel')
