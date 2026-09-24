# GeoJSON организаторов

Положи сюда `*.geojson` (EPSG:4326) — сид подхватит их вместо сгенерированных участков
(`SEED_PARCELS_SOURCE=auto|generated|organizers|both`, по умолчанию `auto`).

Поля маппятся гибко (регистр не важен), см. `apps/api/app/seed/organizers.py`:

| Наше поле | Варианты в исходном файле |
|---|---|
| кадастровый номер | `cadastral_number`, `kad_nomer`, `kadastr`, `cad_num`, `cadnum`, `kn`, `кадастровый_номер`, `кад_номер` |
| назначение | `purpose`, `target`, `celevoe`, `naznachenie`, `назначение`, `целевое_назначение` (текст распознаётся по ключевым словам) |
| площадь | не нужна — считается PostGIS (`ST_Area(geography)`) |
| адрес | `address`, `adres`, `адрес`, `location` |
| владение | `owner_type`, `pravo`, `right`, `вид_права` |
| статус | `status` (наши значения), иначе `OK` |

Если кадастрового номера нет — генерируется `06:097:8xx:nnn` с пометкой `source=organizers`.
