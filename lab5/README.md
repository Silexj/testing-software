# Лабораторная работа 5

Разработка автотестов для Redfish API с использованием PyTest.

Ветка: [lab5-redfish-pytest](https://github.com/Silexj/testing-software/tree/lab5-redfish-pytest/lab5).

## Подготовка и запуск

Требования: Python 3.11+, `ipmitool`, запущенный OpenBMC (см. корневой README).
Команды выполняются из корня репозитория:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r lab5/requirements.txt
export BMC_URL=https://127.0.0.1:2443
export BMC_USERNAME=root
read -rsp 'Пароль OpenBMC: ' BMC_PASSWORD; echo
export BMC_PASSWORD
# Только для лабораторного образа с самоподписанным сертификатом:
export BMC_VERIFY_TLS=false
bash lab5/run_tests.sh
```

Лог и JUnit XML сохраняются в `results/`. Скрипт возвращает код ошибки PyTest,
в том числе при недоступности API. По умолчанию отсутствие датчиков — ошибка.
Для QEMU без физических CPU-датчиков допускается явно указать:

```bash
bash lab5/run_tests.sh --allow-missing-sensors
```

Тогда только отсутствие датчиков приводит к `SKIPPED`; неверные показания,
нарушенные пороги, ошибки HTTP и IPMI остаются ошибками. Пропуск не считается
подтверждением исправности CPU. Набор обращается к реальному BMC, подмен API нет.

## Сценарии

| ID | Функция в test_redfish.py | Проверка |
|---|---|---|
| TC-API-01 | test_authentication | Создание сессии, X-Auth-Token, Location и чтение сессии |
| TC-API-02 | test_system_information | GET системы, HTTP 200, Status и PowerState |
| TC-API-03 | test_power_on | ResetType=On, HTTP 202/204, ожидание On; восстановление Off |
| TC-API-04 | test_cpu_temperature | Каждый CPU-датчик, Celsius, Status, все заданные нижние/верхние пороги |
| TC-API-05 | test_cpu_redfish_matches_ipmi | Все CPU-датчики сопоставлены с IPMI, единицы и состояние корректны, расхождение в пределах допуска |

Сессия переиспользуется через `pytest.fixture(scope="session")`, удаляется в `finally`.
Requests использует тайм-аут, проверку HTTP/JSON, запрещает редиректы и внешние
ссылки с токеном; лог содержит методы, пути и HTTP-коды, без паролей и токенов.
Тест питания изменяет состояние учебного хоста и восстанавливает исходное `Off`.

## Конфигурация

| Переменная | Значение по умолчанию | Назначение |
|---|---|---|
| BMC_URL | https://127.0.0.1:2443 | Адрес Redfish |
| BMC_USERNAME | root | Пользователь |
| BMC_PASSWORD | обязательна | Пароль, не хранится в Git |
| BMC_VERIFY_TLS | true | Проверка сертификата |
| BMC_CA_BUNDLE | не задана | Путь к доверенному CA, предпочтителен отключению TLS |
| BMC_SYSTEM_PATH | /redfish/v1/Systems/system | URI системы |
| BMC_TIMEOUT | 30 | Тайм-аут HTTP, секунды |
| BMC_POWER_TIMEOUT | 90 | Ожидание состояния питания, секунды |
| IPMI_HOST / IPMI_PORT | 127.0.0.1 / 2623 | IPMI LAN+ |
| IPMI_USERNAME / IPMI_PASSWORD | root / BMC_PASSWORD | Учётные данные IPMI |
| CPU_SENSOR_MAP | {} | JSON: MemberId Redfish → точное имя IPMI |
| CPU_TOLERANCE_C | 2 | Допуск сравнения, градусы Celsius |

Например: `export CPU_SENSOR_MAP='{"cpu0":"CPU0 Temp","cpu1":"CPU1 Temp"}'`.
Нормализация регистра и разделителей допустима; неоднозначное совпадение — ошибка.
IPMI-показание сравнивается с интервалом двух Redfish-измерений с допуском 2 °C
на квантование IPMI и изменение температуры. Для нормы температуры используются
пороги самого датчика; универсальное значение «85 °C» не предполагается.
Поддерживается модель `Chassis/*/Thermal/Temperatures` из используемого OpenBMC.

## Уточнения к методичке и документация

В методичке для создания сессии указан HTTP 200. По Redfish возвращается
`201 Created`; тест допускает 200 и 201, проверяя токен и созданную сессию.
Для Reset методичка требует 202, а Redfish допускает синхронное завершение с 204.
Оба успешных кода допустимы, но тест обязательно проверяет фактическое `PowerState=On`.

- [DMTF DSP0266, сессии и операции](https://redfish.dmtf.org/schemas/DSP0266_1.17.0.html)
- [DMTF Thermal, ReadingCelsius и пороги](https://redfish.dmtf.org/schemas/v1/Thermal.v1_7_3.json)
- [ipmitool, официальный исходный код и документация](https://github.com/ipmitool/ipmitool)
- [PyTest fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)

## Результаты тестирования

Результат: **2 PASSED, 1 FAILED, 2 SKIPPED**, 108,12 с.
Аутентификация и данные системы проверены успешно. On принят с HTTP 204,
но `PowerState` остался `Off` в течение 90 секунд; проверка завершилась ошибкой,
затем выполнен ForceOff и подтверждён Off. Два температурных теста пропущены:
массив `Temperatures` пуст, IPMI не предоставляет числовой температуры CPU.

В `results/environment.json` сохранены ответы API и вывод IPMI;
`pytest.log` и `junit.xml` содержат протокол и результаты проверок.
Полная аппаратная проверка требует стенда с работающим хостом и CPU-датчиками;
на нём запускать без `--allow-missing-sensors`.
