# Лабораторные работы по тестированию ПО

СибГУТИ, ИП-413. Сёмин Д. В., Хайретдинов Д. Д.

Репозиторий используется для всех оставшихся лабораторных. Каждая работа
выполняется в отдельной ветке от `main`, в каталоге `labN/`:

| Работа | Ветка | Содержание |
|---|---|---|
| 5 | [lab5-redfish-pytest](https://github.com/Silexj/testing-software/tree/lab5-redfish-pytest/lab5) | Redfish API, PyTest, сравнение с IPMI |
| 6 | [lab6-locust](https://github.com/Silexj/testing-software/tree/lab6-locust/lab6) | Locust, OpenBMC и публичные API |
| 7 | [lab7-jenkins-ci](https://github.com/Silexj/testing-software/tree/lab7-jenkins-ci/lab7) | Jenkins в Docker, Pipeline QEMU/API/Web UI/Locust |
| 8 | [lab8-profiling](https://github.com/Silexj/testing-software/tree/lab8-profiling/lab8) | Профилирование QEMU: perf, vmstat, nmon и сравнение параметров TCG |

`main` содержит общие инструкции и стенд. Ветки лабораторных независимы:
для следующей работы выполнить `git switch main`, затем `git switch -c labN-topic`.
Не перезаписывать завершённые работы; исправления коммитить в соответствующую ветку.
Код, инструкции, результаты и отчёт находятся внутри каталога работы.

## Общий стенд OpenBMC

Используется образ Romulus из лабораторной №1. Образ и зависимости в Git не добавляются.
Скрипт создаёт рабочую копию flash и запускает QEMU в Docker:

```bash
bash tools/start_openbmc.sh /absolute/path/to/romulus.static.mtd
curl -k https://127.0.0.1:2443/redfish/v1/
```

Загрузка может занять несколько минут. HTTPS: `127.0.0.1:2443`, SSH: `2222`,
IPMI LAN+: UDP `2623`. Порты доступны только локально.
Учётные данные лабораторного образа задаются через `BMC_USERNAME` и `BMC_PASSWORD`.
Остановка: `docker stop testing-software-openbmc`.
Просмотр консоли: `docker logs --tail 100 testing-software-openbmc`.

Образ эмулирует BMC; наличие физических датчиков CPU и работа силовой части
хоста зависят от возможностей QEMU. Отчёты должны отражать реальные ограничения стенда.
