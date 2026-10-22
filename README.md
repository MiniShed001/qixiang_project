# 气象数据可视化系统

基于 Django + SQLite 的气象数据可视化系统,采集六大类真实气象数据并自动生成图表、图像、图文与动画。

## 数据类别与来源(全部免费公开、无需 API key)

| 类别 | 来源 | 内容 |
|------|------|------|
| 地面气象 | Open-Meteo(中国 5 城)+ IEM ASOS(美国 5 站) | 气温/气压/湿度/风/降水,逐小时 |
| 高空气象 | Iowa State Mesonet RAOB 探空档案 | 各气压层温度/露点/风(4 站,每日 2 次) |
| 海洋气象 | NOAA NDBC 浮标 | 有效波高/波周期/海温/气温/气压/风(5 浮标) |
| 天气雷达 | IEM 全国雷达拼图 | 基本反射率 n0q,8 时次 |
| 国外卫星 | GOES-16(AWS 开放桶) | ABI 红外 10.3µm 云图,netCDF 解析渲染 |
| 风云卫星 | NSMC(需实名注册) | FY-4A/4B AGRI L1,管线已就绪 |

## 快速开始

```bash
cd /home/lihui/django_workspace/mysite
../venv/bin/python manage.py runserver 0.0.0.0:8000
# 浏览器打开 http://127.0.0.1:8000/
```

## 常用命令

```bash
# 重新抓取并入库所有数据(SQLite)
../venv/bin/python manage.py ingest_data

# 重新生成图表与动画
../venv/bin/python manage.py make_visuals

# 后台管理(http://127.0.0.1:8000/admin/ 需先 createsuperuser)
../venv/bin/python manage.py createsuperuser
```

## 目录结构

```
meteo/
  models.py                    # 6 类数据模型
  fetch.py                     # 数据抓取与解析(含风云管线骨架)
  plotting.py                  # 可视化(图表/Skew-T/云图/GIF)
  management/commands/
    ingest_data.py             # 入库命令
    make_visuals.py            # 可视化命令
  static/meteo/plots/          # 静态图(PNG)
  static/meteo/img/            # 动画(GIF)
  templates/meteo/             # 网页(中文界面)
media/                         # 雷达图、卫星云图原图
data/raw/                      # GOES netCDF 等原始文件
```

## 风云卫星数据获取步骤

风云四号(FY-4A/4B)数据由国家卫星气象中心(NSMC)管理,要求实名注册:

1. 打开 https://satellite.nsmc.org.cn 注册并通过实名认证(约 1 个工作日)
2. 登录后按 卫星/仪器/产品/时间 检索,提交订单下载 FY-4 AGRI L1 数据(HDF5,含 14 通道)
3. 在 `meteo/fetch.py` 的 `fetch_fy4()` 中接入账号凭证,即可自动检索、下单、下载
4. 用 satpy 的 `agri_l1` reader 解析 HDF5,渲染云图(参考 https://github.com/zxdawn/FY-4)

## 可视化清单

- 图表:地面温度/气压时序、风玫瑰图、Skew-T 斜温图、温湿垂直廓线、波高/海温时序、风速-波高散点
- 交互:Chart.js 时序图(可开关站点)、Plotly 站点/浮标分布地图
- 图像:雷达拼图、GOES 红外云图
- 动画:雷达回波演变(8 帧)、GOES 云图演变(5 帧)、波高演变动画(48 帧)
