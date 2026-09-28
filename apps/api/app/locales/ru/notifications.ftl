## Уведомления жителю (Notifier)

notify-signal-status = 🔔 Обращение { $code }: { $status }
notify-reason = Причина: { $reason }
notify-signal-confirmed-hint = Инспектор зафиксировал нарушение. Мы сообщим, когда оно будет устранено.
notify-parcel-status = 🔔 По вашему обращению { $code } (участок { $cadastral }): { $status }
notify-application-status = 🔔 Заявление { $number }: { $status }
application-inspection-date = 📅 Дата выезда инспектора: { $date }
btn-show-application = Открыть заявление

## Статусы

signal-status-NEW = 🆕 принято, ожидает рассмотрения
signal-status-IN_REVIEW = 🔎 взято в работу инспектором
signal-status-CONFIRMED = ✅ нарушение подтверждено
signal-status-REJECTED = ❌ нарушение не подтвердилось

parcel-status-OK = 🟢 нарушений нет
parcel-status-UNDER_CHECK = 🟡 участок на проверке
parcel-status-VIOLATION = 🔴 зафиксировано нарушение, владельцу выдан срок на устранение
parcel-status-IN_REMEDIATION = 🛠 нарушение устраняется
parcel-status-RESOLVED = ✅ нарушение устранено
parcel-status-RETURNED_TO_STATE = 🏛 участок возвращён в государственную собственность

application-status-UNDER_REVIEW = ⏳ на рассмотрении
application-status-INSPECTION_SCHEDULED = 🚗 назначен выезд инспектора
application-status-APPROVED = ✅ одобрено
application-status-REJECTED = ❌ отказано

## Справочники (акт, бот)

purpose-IZHS = ИЖС
purpose-AGRICULTURE = Сельскохозяйственное назначение
purpose-COMMERCIAL = Коммерческая деятельность
purpose-INDUSTRIAL = Промышленность
purpose-LPH = ЛПХ
owner-PRIVATE = Частная собственность
owner-LEASE = Аренда
owner-STATE = Государственная собственность
violation-UNUSED = Неиспользование по назначению
violation-SELF_SEIZURE = Самовольный захват
violation-DUMP = Несанкционированная свалка
violation-MISUSE = Нецелевое использование
category-DUMP = Свалка
category-ABANDONED = Заброшенный участок
category-SELF_SEIZURE = Самозахват
category-OTHER = Другое
photo-source-INSPECTOR = Инспектор
photo-source-CITIZEN = Житель
pstatus-OK = Нарушений нет
pstatus-UNDER_CHECK = На проверке
pstatus-VIOLATION = Выявлено нарушение
pstatus-IN_REMEDIATION = Нарушение устраняется
pstatus-RESOLVED = Нарушение устранено
pstatus-RETURNED_TO_STATE = Возвращён в госсобственность
sstatus-NEW = новый
sstatus-IN_REVIEW = в работе
sstatus-CONFIRMED = подтверждён
sstatus-REJECTED = отклонён

## Заявка на землю из Mini App

land-draft-title = 📝 Проверьте заявку { $number }
land-draft-parcel = { $n }. <b>{ $cadastral }</b> — { $area } га, { $address }
land-draft-applicant = 👤 { $name } · ИИН { $iin } · { $phone }
land-draft-priority = Участки указаны в порядке приоритета.
land-draft-confirm-hint = Нажмите «Подтвердить», чтобы отправить заявку в акимат.
btn-land-confirm = ✅ Подтвердить и отправить
btn-land-cancel = ✖️ Отменить
application-status-DRAFT = 📝 ожидает подтверждения
application-status-CANCELLED = ✖️ отменено

## Дистанционная проверка участка

inspection-request = 📷 Земельная инспекция просит фотоотчёт по вашему участку <b>{ $cadastral }</b> (запрос { $code }). Срок — до { $due }.
inspection-request-note = Что снять: { $note }
inspection-request-hint = Откройте проверку, находясь на участке: приложение запросит геолокацию и камеру. Фото из галереи не принимаются.
btn-inspection-open = 📷 Открыть проверку
btn-inspection-browser = Открыть в браузере
inspection-reviewed = 🔔 Фотоотчёт { $code } по участку { $cadastral }: { $status }
inspection-status-ACCEPTED = ✅ принят инспектором
inspection-status-REJECTED = ❌ отклонён инспектором
inspection-status-SUBMITTED = ⏳ на проверке
inspection-status-REQUESTED = ожидает отчёта
inspection-status-EXPIRED = ⌛ срок истёк
