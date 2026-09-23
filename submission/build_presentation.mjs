// Финальная презентация: задача, решение, проверяемые результаты.
// SKILL_DIR, TMP_DIR, FINAL_PPTX, RUNTIME_PYTHON, RUNTIME_NODE_MODULES:
// абсолютные пути. TMP_DIR и FINAL_PPTX должны находиться внутри workspaceDir.
// Все примеры ПД синтетические. Данные измерений приведены с границами применимости.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {SKILL_DIR, TMP_DIR, FINAL_PPTX, RUNTIME_PYTHON, RUNTIME_NODE_MODULES} = process.env;
for (const [key,value] of Object.entries({SKILL_DIR,TMP_DIR,FINAL_PPTX,RUNTIME_PYTHON,RUNTIME_NODE_MODULES})) {
  if (!path.isAbsolute(value ?? '')) throw new Error(`${key} must be an absolute path`);
}
const {importRuntimeModule} = await import(pathToFileURL(path.join(SKILL_DIR,'container_tools/runtime_helpers.mjs')).href);
const {Presentation,PresentationFile,FileBlob} = await importRuntimeModule('@oai/artifact-tool');
const {finalizePresentation} = await import(pathToFileURL(path.join(SKILL_DIR,'container_tools/artifact_tool_utils.mjs')).href);
const P=Presentation.create({slideSize:{width:1280,height:720}});
const C={ink:'#16232D',red:'#C92829',paper:'#F7F5EF',white:'#FFFFFF',gray:'#505C64',line:'#B4B9B9',tint:'#EBE7DE'};
const FONT='DejaVu Sans';
const REF='https://github.com/rp-alpha-vibe/llm-proxy/blob/main/';
const evidenceDate='23 сентября 2026';
let serial=0;
const slideTexts=[];
function text(s,value,x,y,w,h,size=25,color=C.ink,bold=false,align='left',vertical='middle'){
 const q=s.shapes.add({geometry:'textbox',name:`text-${++serial}`,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 q.text=value;q.text.style={typeface:FONT,fontSize:size,color,bold,alignment:align,verticalAlignment:vertical,autoFit:'none',wrap:'square',insets:{left:0,right:0,top:0,bottom:0}};
 slideTexts.at(-1).push(value); return q;
}
function slide(title,refs=[],dark=false){
 const s=P.slides.add();slideTexts.push([]);s.background.fill=dark?C.ink:C.paper;
 text(s,'КРАСНЫЙ KOD',64,32,420,28,16,dark?'#BBC3C8':C.red,true);
 text(s,String(P.slides.items.length).padStart(2,'0'),1150,32,65,28,16,dark?'#BBC3C8':C.gray,false,'right');
 text(s,title,64,97,1152,108,40,dark?C.white:C.ink,true);
 s.speakerNotes.textFrame.setText(`Источники: ТЗ «Модуль безопасности персональных данных», ds.pdf, предоставлен владельцем.\n${refs.map(r=>r.startsWith('https://')?r:REF+r).join('\n')}\nДата подготовки: ${evidenceDate}. Локальные результаты не являются оценкой AlfaSonar.`);
 return s;
}
function note(s,v,dark=false){text(s,v,64,648,1152,48,18,dark?'#BBC3C8':C.gray);}
function label(s,v,x,y,w=520){return text(s,v,x,y,w,38,23,C.red,true);}
function box(s,v,x,y,w,h,{size=23,fill=C.white,color=C.ink,bold=false,border=C.line}={}){
 const q=s.shapes.add({geometry:'rect',name:`diagram-${++serial}`,position:{left:x,top:y,width:w,height:h},fill,line:{fill:border,width:1.5}});
 q.text=v;q.text.style={typeface:FONT,fontSize:size,color,bold,alignment:'center',verticalAlignment:'middle',autoFit:'none',wrap:'square',insets:{left:14,right:14,top:10,bottom:10}};
 slideTexts.at(-1).push(v);return q;
}
function connect(s,a,b,from='right',to='left',color=C.red){
 return s.shapes.connect(a,b,{kind:'elbow',fromSide:from,toSide:to,line:{fill:color,width:2},tail:{type:'triangle',width:'sm',length:'sm'}});
}
function rule(s,x,y,w){s.shapes.add({geometry:'line',position:{left:x,top:y,width:w,height:0},fill:'none',line:{fill:C.line,width:1}});}
function table(s,headers,rows,y,widths,rowH=69){
 const vals=[headers,...rows];const t=s.tables.add({rows:vals.length,columns:headers.length,left:64,top:y,width:1152,height:rowH*vals.length,values:vals,columnWidths:widths});
 vals.forEach((r,i)=>{t.rows[i].height=rowH;r.forEach((v,j)=>{const c=t.getCell(i,j);c.fill=i===0?C.ink:i%2?C.white:C.paper;c.text.style={typeface:FONT,fontSize:i===0?20:21,color:i===0?C.white:C.ink,bold:i===0,wrap:'square',verticalAlignment:'middle',insets:{left:14,right:12,top:8,bottom:8}};slideTexts.at(-1).push(v);});});return t;
}
function link(s,v,url,x,y,w,size=22){const q=text(s,v,x,y,w,46,size,C.ink);q.text=[[{run:v,link:{uri:url,isExternal:true}}]];}
// 1. Назначение сервиса.
{
 const s=slide('Сервис для защиты персональных\nданных при работе с LLM',['docs/REQUIREMENTS.md'],true);
 text(s,'Сервис предназначен для обнаружения и маскирования\nперсональных данных в запросах к LLM и их восстановления\nв ответах модели.',66,275,1120,175,29,C.white);
 text(s,'llm-proxy',66,529,600,60,35,C.red,true);
 note(s,'Команда Красный Kod. Хакатон АльфаВайб. 23 сентября 2026',true);
}
// 2. Исходная проблема и обязательные ограничения, без нумерованного чек-листа.
{
 const s=slide('Исходная задача',['docs/REQUIREMENTS.md']);
 text(s,'Команды банка защищают ПД в запросах к LLM разными способами.\nТакие решения трудно переиспользовать и настраивать,\nа восстановление данных реализовано не везде.',64,227,1148,135,28);
 label(s,'Требуемое решение',64,390);
 text(s,'Общий сервис маскирования ПД с обратимыми заменами,\nправилами для разных систем и возможностью добавлять новые типы.',64,437,1145,90,27);
 rule(s,64,566,1152);
 text(s,'Ориентиры ТЗ: качество 95%, 1000 запросов/с, ответ до 1 с,\nтексты до 100 000 токенов.',64,588,1152,65,24,C.gray);
}
// 3. Схема обмена. LLM вызывается приложением.
{
 const s=slide('Взаимодействие с LLM',['docs/MASKING.md','src/llm_proxy/application/process_service.py']);
 const a=box(s,'Система-потребитель',70,234,420,70,{bold:true});
 const b=box(s,'Сервис маскирования ПД',700,234,510,70,{bold:true});
 const c=box(s,'Система-потребитель',70,393,420,70,{bold:true});
 const d=box(s,'LLM',700,393,510,70,{bold:true});
 const e=box(s,'Система-потребитель',70,552,420,70,{bold:true});
 const f=box(s,'Сервис маскирования ПД',700,552,510,70,{bold:true});
 connect(s,a,b);connect(s,c,d);connect(s,e,f);
 label(s,'Запрос с ПД',70,190,520);label(s,'Маскированный запрос',70,349,610);label(s,'Ответ LLM с масками',70,508,610);
 text(s,'Возвращает текст с масками',715,309,490,35,22,C.gray);
 text(s,'Возвращает ответ с масками',715,468,490,35,22,C.gray);
 text(s,'Возвращает ответ с исходными ПД',715,627,490,35,22,C.gray);
}
// 4. Настоящая компонентная схема, редактируемые узлы и связи.
{
 const s=slide('Архитектура сервиса',['docs/ARCHITECTURE.md','src/llm_proxy/main.py']);
 const api=box(s,'HTTP API\nFastAPI',64,297,200,122,{bold:true});
 const flow=box(s,'ProcessService\nсессия и режим обработки',363,297,288,122,{fill:C.ink,color:C.white,bold:true});
 const engine=box(s,'PII Engine\nпоиск и границы ПД',750,254,440,98);
 const masks=box(s,'Маскирование\nи восстановление',750,413,440,98);
 const policy=box(s,'Политики систем\nкатегории и разрешения',363,207,288,66,{size:20});
 const store=box(s,'Redis\nAES-GCM, TTL',363,524,288,95,{bold:true});
 connect(s,api,flow);connect(s,flow,engine);connect(s,flow,masks);connect(s,policy,flow,'bottom','top',C.gray);connect(s,flow,store,'bottom','top');
 text(s,'POST /process',65,245,220,36,22,C.gray);
 text(s,'Общая память для\nрабочих процессов',65,543,250,64,21,C.gray);
 text(s,'Локальная обработка текста\nбез внешних NLP-вызовов',750,556,445,64,22,C.gray);
 note(s,'Один сервис приложения и приватный Redis. Docker обеспечивает воспроизводимый запуск.');
}
// 5. Инженерные причины выбора.
{
 const s=slide('Обоснование выбора стека',['docs/DECISIONS.md','docs/ARCHITECTURE.md']);
 const rows=[
 ['Python + FastAPI','Обработка текста, строгая схема запроса и простой HTTP API.'],
 ['Локальные правила поиска','Контроль границ и контекста без передачи ПД внешним моделям.'],
 ['Redis + AES-GCM','Общее состояние для процессов, атомарное создание сессий и TTL.'],
 ['Uvicorn + Docker','Несколько рабочих процессов и воспроизводимое развёртывание.'],
 ['Prometheus + k6','Наблюдение за сервисом и измерение поведения под нагрузкой.']];
 rows.forEach((r,i)=>{const y=223+i*80;text(s,r[0],64,y,348,61,25,C.ink,true);text(s,r[1],454,y,748,61,24,C.gray);if(i<4)rule(s,64,y+72,1152);});
}
// 6. Категории сгруппированы по смыслу, без спорного подсчёта «22 категории ТЗ».
{
 const s=slide('Данные, которые маскирует сервис',['docs/REQUIREMENTS.md','src/llm_proxy/detection/models.py']);
 const cols=[
 ['О человеке','ФИО\nДата рождения\nМесто рождения\nГражданство'],
 ['Документы','Серия и номер паспорта\nОрган выдачи\nКод подразделения\nДата выдачи\nВодительское удостоверение\nИНН'],
 ['Адрес и связь','Адрес и его части:\nстрана, индекс, город,\nулица, дом, квартира\nТелефон\nEmail'],
 ['Банковские данные','Номер карты\nCVV\nПИН-код\nИмя держателя карты']];
 cols.forEach((g,i)=>{const x=64+i*292;label(s,g[0],x,243,276);text(s,g[1],x,310,274,270,22,C.ink,false,'left','top');});
 note(s,'Набор правил охватывает типы из ТЗ. Качество проверяется отдельно на размеченных примерах.');
}
// 7. Поиск с учётом контекста и расширяемости.
{
 const s=slide('Методика поиска ПД',['src/llm_proxy/detection/engine.py','docs/REQUIREMENTS.md']);
 const nodes=[
 box(s,'Нормализация\nтекста',64,251,228,97),
 box(s,'Поиск\nкандидатов',365,251,228,97),
 box(s,'Проверка\nконтекста',668,251,228,97),
 box(s,'Выбор типа\nи границ',971,251,244,97)];
 nodes.slice(0,3).forEach((a,i)=>connect(s,a,nodes[i+1]));
 text(s,'Сохраняем связь\nс позициями\nисходной строки.',64,379,244,130,23,C.gray);
 text(s,'Шаблоны, метки\nполей, форматы\nи контрольные суммы.',365,379,257,130,23,C.gray);
 text(s,'Отличаем ПД\nот обычной даты\nили адреса банка.',668,379,248,130,23,C.gray);
 text(s,'Разрешаем\nпересечения.\nСохраняем остальной текст.',971,379,245,145,23,C.gray);
 note(s,'Новые правила подключаются через реестр детекторов. HTTP-контракт и работа сессий сохраняются.');
}
// 8. Вместо классификации способов демаскирования — два понятных примера.
{
 const s=slide('Маскирование и восстановление',['docs/MASKING.md','tests/test_product_demask.py']);
 label(s,'Входные данные',64,225,490);label(s,'Выходные данные',715,225,490);
 text(s,'Маскирование запроса',64,292,1152,40,25,C.ink,true);
 const a=box(s,'Напишите на demo@example.com.',64,353,505,82,{size:24});
 const b=box(s,'Напишите на <EMAIL_1>.',715,353,501,82,{size:24});connect(s,a,b);
 text(s,'Восстановление ответа модели',64,472,1152,40,25,C.ink,true);
 const c=box(s,'Ответ отправлен на <EMAIL_1>.',64,534,505,82,{size:24});
 const d=box(s,'Ответ отправлен на demo@example.com.',715,534,501,82,{size:23});connect(s,c,d);
 note(s,'Один payload_id связывает запрос и ответ. Текст ответа сохраняется. Пример синтетический.');
}
// 9. Контракт и настройка потребителей.
{
 const s=slide('HTTP-контракт и политики систем',['docs/REQUIREMENTS.md','config/systems.example.yaml']);
 label(s,'POST /process',64,225,520);
 text(s,'Запрос',64,290,450,35,22,C.gray);
 text(s,'{\n  "payload": "строка для обработки",\n  "payload_id": "идентификатор"\n}',64,331,610,155,25);
 text(s,'Ответ 200',64,517,520,35,22,C.gray);
 text(s,'{ "result": "обработанная строка" }',64,560,627,53,24);
 label(s,'Настройки в YAML',744,225,470);
 text(s,'Разрешение обращения\nКатегории ПД\nРазрешение восстановления\nФормат масок',744,303,470,211,25);
 text(s,'Новый потребитель добавляется\nчерез конфигурацию.',744,552,470,68,23,C.gray);
 note(s,'В текущем deployment система задана конфигурацией. Авторизации отправителя в публичном API нет.');
}
// 10. Состояние определяется наличием сессии и содержимым payload, а не счётчиком запросов.
{
 const s=slide('Жизненный цикл сессии',['src/llm_proxy/application/process_service.py','src/llm_proxy/state/redis_store.py']);
 const req=box(s,'Запрос\npayload_id + payload',64,249,255,78,{size:22});
 const lookup=box(s,'Поиск сессии\nсистема + payload_id',420,249,355,78,{size:22});connect(s,req,lookup);
 const absent=box(s,'Сессии нет\nПоиск ПД и маскирование',64,394,480,88,{size:23});
 const existing=box(s,'Сессия найдена\nСравнение payload',695,394,520,88,{size:23});
 connect(s,lookup,absent,'bottom','top');connect(s,lookup,existing,'bottom','top');
 text(s,'Создать зашифрованную запись в Redis.\nTTL после маскирования: 15 минут.\nВернуть маскированный текст.',64,517,535,115,22);
 text(s,'Исходный текст: вернуть прежнюю маску.\nМаска: вернуть исходную строку.\nОтвет LLM: восстановить известные маски.',695,507,520,116,22);
 note(s,'После восстановления TTL = 2 минуты. По истечении TTL Redis удаляет запись. Сроки настраиваются.');
 s.speakerNotes.textFrame.setText('Источники: '+REF+'src/llm_proxy/application/process_service.py\n'+REF+'src/llm_proxy/state/redis_store.py\nДетали: ключ привязан к системе и payload_id. SET NX предотвращает перезапись при конкурентном создании. При существующей сессии сначала проверяется payload == original_text, затем masked_text, затем выполняется восстановление известных масок. После demask EXPIRE устанавливает TTL 120 с заново. При allow_demask=false возвращается 403. После утраты сессии новый запрос обрабатывается как создание сессии, исходные значения восстановить невозможно. Redis недоступен: 503. Сроки 900/120 с — значения по умолчанию.');
}
// 11. Наблюдаемость с точным смыслом метрик.
{
 const s=slide('Логи, метрики и наблюдаемость',['src/llm_proxy/observability/metrics.py','src/llm_proxy/observability/logging.py']);
 label(s,'Логи обработки',64,239,510);
 text(s,'Операция и код ответа\nТипы и число найденных ПД\nВремя поиска и обращения к Redis',64,305,520,190,26);
 label(s,'Метрики /metrics',704,239,510);
 text(s,'Latency: время ответа\nRPS: запросы в секунду\nTPS: текстовые единицы в секунду\nОшибки, 429 и активные запросы',704,305,512,190,26);
 rule(s,64,543,1152);
 text(s,'Исходный текст и значения ПД не включаются в логи и метрики.\nСоответствия для восстановления хранятся в Redis под AES-GCM.',64,567,1152,72,24);
 note(s,'TPS использует разделение по пробелам. Это не токенизатор конкретной LLM.');
}
// 12. Пример инженерной работы и измеренного улучшения, без необъяснённых метрик.
{
 const s=slide('Улучшение поиска в анкетах',['docs/TASK_IMPROVE_PII_DETECTION.md','scripts/eval_labeled_sample.py','https://github.com/rp-alpha-vibe/llm-proxy/commit/73153457f2b6aba31b61d933b45636d56ee961ee']);
 text(s,'Проверка: 200 синтетических анкет по 22 поля.\nВсего 4400 значений, которые нужно закрыть маской правильного типа.',64,221,1152,97,26);
 label(s,'До доработки',64,358,470);label(s,'Текущая версия',704,358,490);
 text(s,'1 902 из 4 400',64,407,560,76,43,C.ink,true);
 text(s,'4 400 из 4 400',704,407,512,76,43,C.red,true);
 text(s,'43,23% полей полностью закрыты',64,486,570,46,23,C.gray);
 text(s,'100% полей полностью закрыты',704,486,512,46,23,C.gray);
 text(s,'Добавили разбор полей по меткам, границы адресных компонентов\nи варианты дат. Контекстные правила не зависят только от контрольной суммы.',64,554,1152,76,24);
 note(s,'Результат относится к этой выборке анкет. Качество произвольного текста проверяется отдельно.');
 s.speakerNotes.textFrame.setText('ТЗ ds.pdf: §4.1–4.3. До: docs/TASK_IMPROVE_PII_DETECTION.md, baseline f42d0be, 1902/4400. После: свежий запуск 23.09.2026 scripts/eval_labeled_sample.py --sample synthetic_pdn_requests_200_utf8.txt, lines=200, fields_covered=4400/4400, false_positives=0, exact_round_trip=200/200. Исходная выборка вне репозитория. Измеряется полное покрытие поля правильным типом, а не точное совпадение границ: detection.start <= field.start, detection.end >= field.end. Это не официальный scoring и не независимый тест: правила улучшали на этой выборке.\n'+REF+'scripts/eval_labeled_sample.py\n'+REF+'docs/TASK_IMPROVE_PII_DETECTION.md');
}
// 13. Что именно проверяли и что означает результат.
{
 const s=slide('Проверка корректности',['src/llm_proxy/quality/corpus.yaml','src/llm_proxy/quality/runner.py','tests/test_product_demask.py']);
 text(s,'56 синтетических примеров с заранее заданными типами и границами ПД.\nВ набор входят разные форматы, пересечения и тексты без персональных данных.',64,218,1152,85,25);
 table(s,['Что проверяли','Результат на текущем наборе'],[
 ['Тип и точные границы найденных ПД','Все совпали с разметкой'],
 ['Лишние срабатывания и пропуски','0 лишних находок, 0 пропусков'],
 ['Маскирование и обратное восстановление','Исходная строка восстановлена в 56 из 56 примеров']
 ],335,[510,642],69);
 note(s,'Локальные тесты не подтверждают порог 95% на скрытом наборе AlfaSonar. Внешний результат открыт.');
}
// 14. Производительность: цели и измерения с честным разделением окружений.
{
 const s=slide('Результаты нагрузочных испытаний',['docs/ARCHITECTURE.md','submission/railway-load-probe-2026-09-23.md']);
 text(s,'Цель ТЗ: 1000 запросов/с, ориентир времени ответа до 1 с.\nПрофиль команды: 300 секунд после прогрева, маскирование и восстановление.',64,215,1152,83,25);
 table(s,['Метрика','Локально, 8 процессов','Railway'],[
 ['Успешных операций/с','≈1000','≈645'],
 ['Время ответа для 95% операций','≤21,78 мс','≈10 с'],
 ['Ошибки','0','≈33%']
 ],322,[485,345,322],68);
 text(s,'На локальном профиле цель достигнута. Публичный deployment\nвыдержал короткий тест 100 запросов/с, но не прошёл профиль 1000 запросов/с.',64,602,1152,63,23);
 s.speakerNotes.textFrame.setText('Источники: '+REF+'docs/ARCHITECTURE.md\n'+REF+'submission/railway-load-probe-2026-09-23.md\nМетрики из сохранённых прогонов, повторно в рамках изменения слайдов не запускались. Локально 300001/300=1000.003 уникальных успешных операций/с, p95=21.78 мс, 0 ошибок и 429. Railway 193444/300=644.813 успешных операций/с, p95 около 10 с, ошибки около 33%, 76483 ответа 429. Короткий Railway probe: 100/с в течение 30 с, ошибок нет. Одна операция — маскирование либо восстановление; пара содержит две операции. 100000 условных токенов проверялись отдельно, а не при 1000 RPS. Эти показатели не характеризуют все возможные payload и текущую версию без нового прогона.');
}
// 15. Завершение: результат, границы и прямые ссылки на демонстрацию.
{
 const s=slide('Результат проекта',['README.md','submission/CHECKLIST.md']);
 label(s,'Реализовано',64,229,600);
 text(s,'Сервис маскирования ПД с обратным восстановлением,\nнастройками систем и зашифрованными сессиями.\nЛокальные проверки подтверждают работу на тестовых наборах.',64,283,1152,133,28);
 label(s,'Остаётся подтвердить',64,446,620);
 text(s,'Качество и совместимость в AlfaSonar, внешнюю проверку ZIP\nи целевую нагрузку на публичном сервере.',64,493,1152,76,25,C.gray);
 link(s,'Демонстрация API','https://llm-proxy-production-84c7.up.railway.app/docs',64,589,480,24);
 link(s,'Исходный код на GitHub','https://github.com/rp-alpha-vibe/llm-proxy',704,589,512,24);
 note(s,'Публичный API предназначен для синтетических данных. Соответствие стандартам ИБ банка не подтверждено.');
}
await fs.mkdir(TMP_DIR,{recursive:true});
await fs.mkdir(path.dirname(FINAL_PPTX),{recursive:true});
const candidate=path.join(TMP_DIR,'candidate.pptx');
await (await PresentationFile.exportPptx(P)).save(candidate);
const workspaceDir=path.resolve(process.env.WORKSPACE_DIR ?? path.dirname(TMP_DIR));
await finalizePresentation({workspaceDir,candidatePath:candidate,finalPath:FINAL_PPTX,pythonExecutable:RUNTIME_PYTHON,
 integrityValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit','--require-native-table-slide','13','--require-native-table-slide','14'],
 explicitTotalSlideCount:15,requiredNativeTableOwnerSlides:[13,14],fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,
 receiptPath:path.join(TMP_DIR,'validation.json')});
// Render the finalized PPTX, so previews and PDF correspond to the delivered package.
const finalDeck=await PresentationFile.importPptx(await FileBlob.load(FINAL_PPTX));
const previews=path.join(TMP_DIR,'rendered');await fs.mkdir(previews,{recursive:true});
for(let i=0;i<finalDeck.slides.items.length;i++){
 const preview=await finalDeck.export({slide:finalDeck.slides.items[i],format:'png',scale:2});
 await fs.writeFile(path.join(previews,`slide-${i+1}.png`),new Uint8Array(await preview.arrayBuffer()));
 console.log(`Rendered ${i+1}/15`);
}
await fs.writeFile(path.join(TMP_DIR,'slide-text.json'),JSON.stringify(slideTexts,null,2));
console.log(JSON.stringify({slides:15,pptx:FINAL_PPTX,previews}));
