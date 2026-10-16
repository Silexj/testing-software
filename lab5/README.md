# Лабораторная работа 5

Разработка автотестов для Redfish API с использованием PyTest.

Ветка: [lab5-redfish-pytest](https://github.com/Silexj/testing-software/tree/lab5-redfish-pytest/lab5).

## Подготовка и запуск

Требования: Python 3.11+, `ipmitool`, Docker и запущенный OpenBMC Romulus
из лабораторной 1 (см. корневой README). Команды из корня репозитория:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r lab5/requirements-stand.txt
export BMC_URL=https://127.0.0.1:2443
export BMC_USERNAME=root
read -rsp 'Пароль OpenBMC: ' BMC_PASSWORD; echo
export BMC_PASSWORD
# Для самоподписанного сертификата учебного стенда:
export BMC_VERIFY_TLS=false
# Первичная сборка и установка аппаратного профиля в работающий QEMU:
python lab5/setup_qemu_lab.py install --qemu --build
python lab5/setup_qemu_lab.py status --qemu
bash lab5/run_tests.sh
```

Перед установкой эмулируемый хост должен быть выключен. Проверяется точный
образ Romulus `BUILD_ID=20250902012112`. После перезагрузки BMC профиль нужно
установить снова; при сохранённом `.runtime/lab5-build` можно убрать `--build`.

QEMU эмулирует контроллер BMC, но не POWER9, силовую часть и CPU-датчики платы.
Поэтому для полного учебного прогона установлен явный аппаратный профиль:
модель PSU/FSI/VRM и два управляемых входа hwmon с начальными значениями 42/44 °C.
Штатные `phosphor-state-manager`, `phosphor-hwmon`, bmcweb и ipmid продолжают
обрабатывать переходы питания, датчики, пороги и запросы. Дополнительно исправлен
устаревший масштаб двух CPU-датчиков в таблице IPMI выбранного образа: Celsius
вместо прежних миллиградусов. Устройство профиля и удаление описаны в
[stand/README.md](stand/README.md).

Это интеграционная проверка ПО OpenBMC на управляемой модели оборудования.
Значения 42/44 °C заданы стендом и не являются измерениями физических CPU.
На физическом BMC аппаратный профиль устанавливать не нужно; достаточно
`requirements.txt` и адресов реального Redfish/IPMI.

Лог и JUnit XML сохраняются в `lab5/results/`. Скрипт возвращает код ошибки
PyTest. Отсутствующие CPU-датчики, недостигнутое состояние питания, неверные
показания, нарушения порогов и ошибки API приводят к ошибке; пропусков нет.

## Сценарии

| ID | Функция в test_redfish.py | Проверка |
|---|---|---|
| TC-API-01 | test_authentication | Создание сессии, X-Auth-Token, Location и чтение сессии |
| TC-API-02 | test_system_information | GET системы, HTTP 200, Status и PowerState |
| TC-API-03 | test_power_on | Переход Off → On, HTTP 202/204, подтверждение On и восстановление исходного состояния |
| TC-API-04 | test_cpu_temperature | Каждый CPU-датчик, Celsius, Status, все заданные нижние/верхние пороги |
| TC-API-05 | test_cpu_redfish_matches_ipmi | Все CPU-датчики сопоставлены с IPMI, единицы и состояние корректны, расхождение в пределах допуска |

Сессия переиспользуется через `pytest.fixture(scope="session")`, удаляется в `finally`.
Requests использует тайм-аут, проверку HTTP/JSON, запрещает редиректы и внешние
ссылки с токеном; лог содержит методы, пути и HTTP-коды, без паролей и токенов.
Если хост изначально включён, тест сначала выключает его, затем проверяет
включение и в `finally` восстанавливает исходное состояние.

## Конфигурация

| Переменная | Значение по умолчанию | Назначение |
|---|---|---|
| BMC_URL | https://127.0.0.1:2443 | Адрес Redfish |
| BMC_USERNAME | root | Пользователь |
| BMC_PASSWORD | обязательна | Пароль, не хранится в Git |
| BMC_VERIFY_TLS | true | Проверка сертификата |
| BMC_CA_BUNDLE | не задана | Путь к доверенному CA |
| BMC_SYSTEM_PATH | /redfish/v1/Systems/system | URI системы |
| BMC_TIMEOUT | 30 | Тайм-аут HTTP, секунды |
| BMC_POWER_TIMEOUT | 90 | Ожидание состояния питания, секунды |
| IPMI_HOST / IPMI_PORT | 127.0.0.1 / 2623 | IPMI LAN+ |
| IPMI_USERNAME / IPMI_PASSWORD | root / BMC_PASSWORD | Учётные данные IPMI |
| CPU_SENSOR_MAP | {} | JSON: MemberId Redfish → точное имя IPMI |
| CPU_TOLERANCE_C | 2 | Допуск сравнения, градусы Celsius |

Например: `export CPU_SENSOR_MAP='{"cpu0":"CPU0 Temp","cpu1":"CPU1 Temp"}'`.
Поддерживаются имена OpenPOWER `p0_core0_temp` и `p1_core0_temp`.
Нормализация регистра и разделителей допустима; неоднозначное совпадение — ошибка.
IPMI сравнивается с интервалом двух свежих Redfish-измерений с допуском 2 °C
на квантование IPMI и изменение температуры. Норма определяется порогами
датчика, без универсального значения «85 °C». Используется модель
`Chassis/*/Thermal/Temperatures` выбранного OpenBMC.

## Контроль обнаружения неисправностей

На установленном локальном профиле, при исходном питании Off:

```bash
python lab5/verify_faults.py --qemu
bash lab5/run_tests.sh
```

Скрипт поочерёдно задаёт 95 °C, неверное сопоставление CPU с IPMI и отказ
включения PSU. Для каждой неисправности требуется конкретная ошибка теста
(PyTest exit 1); случайный сбой авторизации не принимается за обнаружение дефекта.
После проверки скрипт восстанавливает 42/44 °C и снимает отказ PSU.
Ожидаемые ошибки сохраняются отдельно в `results/negative_*.log`.

## Уточнения к методичке и документация

В методичке для создания сессии указан HTTP 200. По Redfish возвращается
`201 Created`; тест допускает 200 и 201, проверяя токен и созданную сессию.
Для Reset методичка требует 202, а Redfish допускает синхронное завершение с 204.
Оба кода допустимы, но тест обязательно проверяет фактическое `PowerState=On`.

- [DMTF DSP0266, сессии и операции](https://redfish.dmtf.org/schemas/DSP0266_1.17.0.html)
- [DMTF Thermal, ReadingCelsius и пороги](https://redfish.dmtf.org/schemas/v1/Thermal.v1_7_3.json)
- [ipmitool, исходный код и документация](https://github.com/ipmitool/ipmitool)
- [PyTest fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)

## Результаты тестирования

Полный прогон на аппаратном профиле OpenBMC/QEMU: **5 PASSED, 0 FAILED, 0 SKIPPED**.
Питание действительно проходит Off → On → Off, что подтверждается свежими GET.
Оба CPU-датчика имеют состояние Enabled/OK, температуры 42 и 44 °C и по четыре
проверенных порога. IPMI возвращает те же 42 и 44 °C.

`results/pytest.log` и `results/junit.xml` содержат итоговый успешный прогон;
`environment.json` — снимок API/IPMI и описание аппаратного профиля;
`stand.log` — диагностику служб. Контрольные неисправности и их ожидаемые ошибки
хранятся отдельно от итогового прогона.
