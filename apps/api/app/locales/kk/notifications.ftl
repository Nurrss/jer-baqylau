## Тұрғынға хабарламалар (Notifier)
## Қазақша мәтіндер — ана тілі иесінің тексеруін қажет етеді.

notify-signal-status = 🔔 { $code } өтініші: { $status }
notify-reason = Себебі: { $reason }
notify-signal-confirmed-hint = Инспектор бұзушылықты тіркеді. Ол жойылған кезде хабарлаймыз.
notify-parcel-status = 🔔 Сіздің { $code } өтінішіңіз бойынша ({ $cadastral } учаскесі): { $status }
notify-application-status = 🔔 { $number } өтінішхат: { $status }
application-inspection-date = 📅 Инспектордың барып шығу күні: { $date }
btn-show-application = Өтінішхатты ашу

## Мәртебелер

signal-status-NEW = 🆕 қабылданды, қарауды күтуде
signal-status-IN_REVIEW = 🔎 инспектор жұмысқа алды
signal-status-CONFIRMED = ✅ бұзушылық расталды
signal-status-REJECTED = ❌ бұзушылық расталмады

parcel-status-OK = 🟢 бұзушылық жоқ
parcel-status-UNDER_CHECK = 🟡 учаске тексерілуде
parcel-status-VIOLATION = 🔴 бұзушылық тіркелді, иесіне жою мерзімі берілді
parcel-status-IN_REMEDIATION = 🛠 бұзушылық жойылуда
parcel-status-RESOLVED = ✅ бұзушылық жойылды
parcel-status-RETURNED_TO_STATE = 🏛 учаске мемлекет меншігіне қайтарылды

application-status-UNDER_REVIEW = ⏳ қаралуда
application-status-INSPECTION_SCHEDULED = 🚗 инспектордың барып шығуы тағайындалды
application-status-APPROVED = ✅ мақұлданды
application-status-REJECTED = ❌ бас тартылды

## Анықтамалықтар (акт, бот)

purpose-IZHS = ЖТҚ
purpose-AGRICULTURE = Ауыл шаруашылығы мақсаты
purpose-COMMERCIAL = Коммерциялық қызмет
purpose-INDUSTRIAL = Өнеркәсіп
purpose-LPH = ЖҚШ
owner-PRIVATE = Жеке меншік
owner-LEASE = Жалға алу
owner-STATE = Мемлекеттік меншік
violation-UNUSED = Мақсаты бойынша пайдаланбау
violation-SELF_SEIZURE = Өз бетінше басып алу
violation-DUMP = Рұқсатсыз қоқыс үйіндісі
violation-MISUSE = Мақсатсыз пайдалану
category-DUMP = Қоқыс үйіндісі
category-ABANDONED = Иесіз учаске
category-SELF_SEIZURE = Өз бетінше басып алу
category-OTHER = Басқа
photo-source-INSPECTOR = Инспектор
photo-source-CITIZEN = Тұрғын
pstatus-OK = Бұзушылық жоқ
pstatus-UNDER_CHECK = Тексерілуде
pstatus-VIOLATION = Бұзушылық анықталды
pstatus-IN_REMEDIATION = Бұзушылық жойылуда
pstatus-RESOLVED = Бұзушылық жойылды
pstatus-RETURNED_TO_STATE = Мемлекет меншігіне қайтарылды
sstatus-NEW = жаңа
sstatus-IN_REVIEW = жұмыста
sstatus-CONFIRMED = расталды
sstatus-REJECTED = қабылданбады

## Mini App-тан жерге өтінім

land-draft-title = 📝 { $number } өтінімін тексеріңіз
land-draft-parcel = { $n }. <b>{ $cadastral }</b> — { $area } га, { $address }
land-draft-applicant = 👤 { $name } · ЖСН { $iin } · { $phone }
land-draft-priority = Учаскелер басымдық ретімен көрсетілген.
land-draft-confirm-hint = Өтінімді әкімдікке жіберу үшін «Растау» батырмасын басыңыз.
btn-land-confirm = ✅ Растау және жіберу
btn-land-cancel = ✖️ Болдырмау
application-status-DRAFT = 📝 растауды күтуде
application-status-CANCELLED = ✖️ болдырылмады

## Учаскені қашықтан тексеру

inspection-request = 📷 Жер инспекциясы сіздің <b>{ $cadastral }</b> учаскеңіз бойынша фотоесеп сұрайды ({ $code } сұрауы). Мерзімі — { $due } дейін.
inspection-request-note = Нені түсіру керек: { $note }
inspection-request-hint = Тексеруді учаскеде тұрып ашыңыз: қосымша геолокация мен камераны сұрайды. Галереядағы фотолар қабылданбайды.
btn-inspection-open = 📷 Тексеруді ашу
btn-inspection-browser = Браузерде ашу
inspection-reviewed = 🔔 { $cadastral } учаскесі бойынша { $code } фотоесебі: { $status }
inspection-status-ACCEPTED = ✅ инспектор қабылдады
inspection-status-REJECTED = ❌ инспектор қабылдамады
inspection-status-SUBMITTED = ⏳ тексеруде
inspection-status-REQUESTED = есепті күтуде
inspection-status-EXPIRED = ⌛ мерзімі өтті
