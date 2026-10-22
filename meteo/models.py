"""气象数据可视化系统 —— 数据模型。

六大数据类别:
1. 地面气象(SurfaceObservation)
2. 高空气象(UpperAirLevel, 一次探空对应多条层记录)
3. 海洋气象(OceanObservation)
4. 天气雷达(RadarProduct)
5. 风云气象卫星 + 国外气象卫星(SatelliteImage)
"""
from django.db import models


class Station(models.Model):
    """站点/浮标元数据(地面站、高空站、海洋浮标共用)。"""
    KINDS = [
        ('surface', '地面站'),
        ('upperair', '高空站'),
        ('ocean', '海洋浮标'),
    ]
    station_id = models.CharField('站点编号', max_length=20, unique=True)
    name = models.CharField('站点名称', max_length=100)
    latitude = models.FloatField('纬度', null=True, blank=True)
    longitude = models.FloatField('经度', null=True, blank=True)
    kind = models.CharField('类别', max_length=20, choices=KINDS)
    source = models.CharField('数据来源', max_length=80, blank=True)

    class Meta:
        verbose_name = '站点'
        verbose_name_plural = '站点'

    def __str__(self):
        return f'{self.station_id} {self.name}'


class SurfaceObservation(models.Model):
    """地面气象观测(逐小时)。"""
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='surface_obs')
    time = models.DateTimeField('观测时间', db_index=True)
    temperature_c = models.FloatField('气温℃', null=True, blank=True)
    dewpoint_c = models.FloatField('露点℃', null=True, blank=True)
    humidity_pct = models.FloatField('相对湿度%', null=True, blank=True)
    wind_dir_deg = models.FloatField('风向°', null=True, blank=True)
    wind_speed = models.FloatField('风速 m/s', null=True, blank=True)
    pressure_hpa = models.FloatField('气压 hPa', null=True, blank=True)
    precip_mm = models.FloatField('降水量 mm', null=True, blank=True)

    class Meta:
        verbose_name = '地面观测'
        verbose_name_plural = '地面观测'
        ordering = ['time']
        indexes = [models.Index(fields=['station', 'time'])]

    def __str__(self):
        return f'{self.station_id} {self.time:%Y-%m-%d %H:%M}'


class UpperAirLevel(models.Model):
    """高空探测的单个气压层记录。"""
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='upperair_levels')
    time = models.DateTimeField('探空时间', db_index=True)
    pressure_hpa = models.FloatField('气压 hPa')
    height_m = models.FloatField('高度 m', null=True, blank=True)
    temperature_c = models.FloatField('温度℃', null=True, blank=True)
    dewpoint_c = models.FloatField('露点℃', null=True, blank=True)
    wind_dir_deg = models.FloatField('风向°', null=True, blank=True)
    wind_speed_kt = models.FloatField('风速 kt', null=True, blank=True)

    class Meta:
        verbose_name = '高空探测层'
        verbose_name_plural = '高空探测层'
        ordering = ['-pressure_hpa']
        indexes = [models.Index(fields=['station', 'time'])]

    def __str__(self):
        return f'{self.station_id} {self.time:%Y-%m-%d %H:%M} {self.pressure_hpa:.0f}hPa'


class OceanObservation(models.Model):
    """海洋气象观测(浮标)。"""
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='ocean_obs')
    time = models.DateTimeField('观测时间', db_index=True)
    wind_dir_deg = models.FloatField('风向°', null=True, blank=True)
    wind_speed_ms = models.FloatField('风速 m/s', null=True, blank=True)
    gust_ms = models.FloatField('阵风 m/s', null=True, blank=True)
    wave_height_m = models.FloatField('有效波高 m', null=True, blank=True)
    wave_period_s = models.FloatField('波周期 s', null=True, blank=True)
    wave_dir_deg = models.FloatField('波向°', null=True, blank=True)
    pressure_hpa = models.FloatField('气压 hPa', null=True, blank=True)
    air_temp_c = models.FloatField('气温℃', null=True, blank=True)
    water_temp_c = models.FloatField('海温℃', null=True, blank=True)
    dewpoint_c = models.FloatField('露点℃', null=True, blank=True)

    class Meta:
        verbose_name = '海洋观测'
        verbose_name_plural = '海洋观测'
        ordering = ['time']
        indexes = [models.Index(fields=['station', 'time'])]

    def __str__(self):
        return f'{self.station_id} {self.time:%Y-%m-%d %H:%M}'


class RadarProduct(models.Model):
    """天气雷达拼图产品。"""
    time = models.DateTimeField('观测时间', db_index=True)
    product = models.CharField('产品', max_length=20, default='n0q')   # 基本反射率
    region = models.CharField('区域', max_length=20, default='uscomp')  # 美国全国拼图
    image = models.FileField('图像文件', upload_to='radar/')
    source_url = models.URLField('来源链接', blank=True)

    class Meta:
        verbose_name = '雷达产品'
        verbose_name_plural = '雷达产品'
        ordering = ['time']


class SatelliteImage(models.Model):
    """气象卫星云图(风云 + 国外)。"""
    SATELLITES = [
        ('GOES-16', 'GOES-16'),
        ('GOES-18', 'GOES-18'),
        ('Himawari-8', 'Himawari-8'),
        ('FY-4A', '风云四号A'),
        ('FY-4B', '风云四号B'),
    ]
    satellite = models.CharField('卫星', max_length=20, choices=SATELLITES)
    channel = models.CharField('通道/产品', max_length=30)   # C13, true_color, VIS ...
    time = models.DateTimeField('观测时间', db_index=True)
    image = models.FileField('图像文件', upload_to='satellite/')
    source_url = models.URLField('来源链接', blank=True)
    note = models.CharField('备注', max_length=200, blank=True)

    class Meta:
        verbose_name = '卫星云图'
        verbose_name_plural = '卫星云图'
        ordering = ['time']
