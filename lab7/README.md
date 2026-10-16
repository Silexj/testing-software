# Лабораторная работа 7

CI/CD OpenBMC с GitHub, Jenkins в Docker и Jenkinsfile на Groovy.

Ветка: [lab7-jenkins-ci](https://github.com/Silexj/testing-software/tree/lab7-jenkins-ci).
Pipeline находится в корневом [Jenkinsfile](../Jenkinsfile).

## Подготовка Jenkins

Нужны Docker, Python 3 на хосте и исходный образ Romulus из лабораторной 1.
Бинарная прошивка и пароли в Git не добавляются. Из корня репозитория:

```bash
git switch lab7-jenkins-ci
read -rsp 'Пароль OpenBMC: ' BMC_PASSWORD; echo
export BMC_PASSWORD
bash lab7/start_jenkins.sh /absolute/path/to/romulus.static.mtd
```

Первая сборка скачивает Jenkins, плагины, браузер и инструменты. После появления
в журнале `Jenkins is fully up and running` открыть <http://127.0.0.1:8080>.
Пользователь: `labadmin`. Сгенерированный пароль находится в локальном файле
`.runtime/lab7/secrets/admin-password`; посмотреть его можно командой
`cat .runtime/lab7/secrets/admin-password`. В Jenkins включены авторизация и запрет
анонимного чтения. BMC-пароль хранится как Jenkins Secret text с ID
`openbmc-password` и передаётся Pipeline через credentials binding.

Создаётся задача `openbmc-lab7` типа Pipeline from SCM: GitHub-репозиторий,
ветка `lab7-jenkins-ci`, Script Path `Jenkinsfile`. Init-скрипт настраивает только
новый выделенный экземпляр Jenkins; после первого запуска настройки пользователя
не перезаписываются. Повторный запуск контейнера: `docker start testing-software-jenkins`.
Остановка: `docker stop testing-software-jenkins`. Данные сохраняются в отдельном
томе `testing-software-jenkins-home`.

## Что выполняет Pipeline

| Этап | Проверка | Артефакты Jenkins |
|---|---|---|
| Checkout | Получение ветки из GitHub, фиксация commit и инструментов | checkout/commit.txt, tools.txt, packages.txt |
| OpenBMC QEMU | Новая копия flash, запуск QEMU, ожидание API, установка учебного аппаратного профиля | qemu/console.log, boot.json, hardware.log, thermal.json |
| Redfish API | Пять сценариев лабораторной 5, без пропусков | api/junit.xml, pytest.log |
| Selenium Web UI | Вход, отказ неверному пользователю, элементы питания, строки CPU-датчиков | web/junit.xml, pytest.log, PNG и HTML страниц |
| Locust load | 10 пользователей, разгон 2/с, нагрузка 30 с, проверка измеренных критериев | load/junit.xml, summary.json, HTML, CSV, log |
| Завершение | Остановка только QEMU этой сборки, включая случай ошибки | qemu/cleanup.json |

На каждом этапе действует `post { always { archiveArtifacts ... } }`.
JUnit публикует результаты в разделе Tests. Последний `post` сохраняет полный
набор артефактов и останавливает QEMU. Ошибки shell/pytest/Locust не подавляются:
Pipeline получает FAILURE; последующие тестовые этапы пропускаются.
Одновременные сборки запрещены, в учебном Jenkins выделен один executor.
После первого запуска Jenkins проверяет изменения ветки каждые пять минут
(`pollSCM`) и запускает сборку только при изменении commit. Для локального Jenkins
это позволяет работать без публичного webhook и открытия порта в интернет.

## Особенности стенда

QEMU запускается внутри выделенного контейнера Jenkins от непривилегированного
пользователя. Ему доступны только исходная прошивка для чтения, два отдельных
файла паролей и собственный том данных Jenkins. Docker socket и привилегированный
режим не нужны. Порт 8080 опубликован только на localhost. Порты BMC 2443/2222/2623
доступны внутри контейнера и не конфликтуют со стендом лабораторных 5/6 на хосте.

Для каждого запуска исходная flash копируется в workspace. После готовности
OpenBMC устанавливается аппаратный профиль из лабораторной 5: модель PSU/FSI/VRM,
два управляемых входа hwmon 42/44 °C и совместимость масштаба IPMI. Это проверка
ПО OpenBMC с моделью отсутствующего оборудования, не измерение физических CPU.
Сборка двух ARM-модулей выполняется компилятором внутри Jenkins без вложенного Docker.
Профиль рассчитан на Romulus `BUILD_ID=20250902012112`.

Selenium использует Chromium headless и соответствующий Debian chromedriver.
Проверяется реальное содержимое страниц, включая обе строки датчиков и показания.
Тест операций питания в UI проверяет элементы страницы; переход Off → On → Off
проверяется отдельно полноценным API-тестом. Проверка политики lockout из старой
лабораторной 4 не заявляется: удержание пользователя на странице входа само по
себе не доказывает блокировку учётной записи.

Нагрузочный этап использует OpenBMCUser из лабораторной 6. Критерии: Locust exit 0,
обе операции чтения выполнены, достигнуты 10 пользователей, ошибок 0%, p95 ≤ 5000 мс,
созданы и удалены все 10 сессий. Шесть критериев экспортируются в JUnit. Короткий
30-секундный эксперимент не определяет предел производительности.

## Демонстрация преподавателю

1. Открыть GitHub и корневой Jenkinsfile: показать этапы и секции `post`.
2. В Jenkins открыть `openbmc-lab7`: первая сборка запускается через Build Now,
   после неё параметры доступны через Build with Parameters.
3. Оставить `INJECT_API_FAILURE` выключенным и запустить сборку.
4. В Console Output проследить запуск OpenBMC и тестов; дождаться SUCCESS.
5. Открыть Tests, Build Artifacts, JUnit, снимки браузера и HTML/CSV Locust.
6. Для проверки отказа включить `INJECT_API_FAILURE`: API получит неверный пароль,
   этап завершится ошибкой, нижележащие тесты не запустятся, QEMU остановится,
   диагностические отчёты останутся в артефактах. Затем запустить обычную сборку.

## Происхождение сценариев

- API и аппаратный профиль: лабораторная 5, commit `bbf165a`.
- Locust OpenBMCUser и финальный CSV: лабораторная 6, commit `cebb22c`.
- Web UI: CI-адаптация сценариев лабораторной 4 с Chromium и явными проверками
  содержимого вместо одного лишь URL. Пароли вынесены из кода в credentials.

Необходимые файлы включены в ветку 7, чтобы Jenkins собирал одну ветку и не
зависел от переключений локального checkout. Остальные ветки лабораторных сохранены.

## Документация

- [Jenkins в Docker](https://www.jenkins.io/doc/book/installing/docker/)
- [Jenkinsfile и публикация результатов](https://www.jenkins.io/doc/book/pipeline/jenkinsfile/)
- [JUnit и артефакты](https://www.jenkins.io/doc/pipeline/tour/tests-and-artifacts/)
- [Init Groovy scripts](https://www.jenkins.io/doc/book/managing/groovy-hook-scripts/)

## Запуск и выгрузка через API Jenkins

На подготовленном компьютере с Requests в активном Python-окружении:

```bash
python lab7/scripts/jenkins_run.py
python lab7/scripts/jenkins_run.py --inject-api-failure
python lab7/scripts/jenkins_run.py --collect 1
```

Скрипт читает локальный admin-password, использует CSRF crumb и сохраняет
реальные артефакты в `lab7/results/build-N`. Контрольный отказ остаётся FAILURE
в Jenkins; скрипт только проверяет, что это ожидаемый результат. Для обычной
сборки требуется SUCCESS.
