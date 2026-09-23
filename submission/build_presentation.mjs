// Источник финальной презентации. Сборка: запустить из каталога с
// доступным @oai/artifact-tool, указав SKILL_DIR, TMP_DIR, FINAL_PPTX.
// Все примеры персональных данных в слайдах вымышлены.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation, PresentationFile} from '@oai/artifact-tool';

const {SKILL_DIR, TMP_DIR, FINAL_PPTX, RUNTIME_PYTHON} = process.env;
for (const [key, value] of Object.entries({SKILL_DIR, TMP_DIR, FINAL_PPTX, RUNTIME_PYTHON})) {
  if (!path.isAbsolute(value ?? '')) throw new Error(`${key} must be an absolute path`);
}
const {finalizePresentation} = await import(pathToFileURL(path.join(SKILL_DIR, 'container_tools/artifact_tool_utils.mjs')).href);
const P = Presentation.create({slideSize:{width:1280,height:720}});
const C = {dark:'#16232D', red:'#D52D29', paper:'#F7F5EF', pale:'#E6E1D7', gray:'#4F5C63', white:'#FFFFFF', muted:'#A8B3B6'};
const FONT = 'DejaVu Sans';
const REF = 'https://github.com/rp-alpha-vibe/llm-proxy/blob/main/';
let slideNo = 0;

function t(s, text, x, y, w, h, size=24, color=C.dark, opts={}) {
  const sh=s.shapes.add({geometry:'textbox',name:opts.name??`text-${s.shapes.items?.length??Math.random()}`,
    position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  sh.text=text;
  sh.text.style={typeface:FONT,fontSize:size,bold:!!opts.bold,color,alignment:opts.align??'left',
    verticalAlignment:'middle',autoFit:'none',wrap:'square',insets:{left:0,right:0,top:0,bottom:0}};
  return sh;
}
function link(s, text, url, x, y, w, h, size=24) {
  const shape=t(s,text,x,y,w,h,size,C.dark);
  shape.text=[[{run:text,link:{uri:url,isExternal:true}}]];
  return shape;
}
function base(title, lead='', refs=[], dark=false) {
  const s=P.slides.add(); slideNo++;
  s.background.fill=dark?C.dark:C.paper;
  const ink=dark?C.white:C.dark;
  t(s,'КРАСНЫЙ KOD',64,36,365,32,16,dark?C.muted:C.red,{bold:true});
  t(s,String(slideNo).padStart(2,'0'),1154,34,58,34,17,dark?C.muted:C.gray,{align:'right'});
  t(s,title,64,99,1144,102,37,ink,{bold:true});
  if(lead)t(s,lead,65,202,1135,67,19,dark?C.muted:C.gray);
  if(refs.length)s.speakerNotes.textFrame.setText('Источники и условия утверждений:\n'+refs.map(r=>r.startsWith('https://')?r:REF+r).join('\n'));
  return s;
}
function foot(s,txt,dark=false){t(s,txt,64,658,1150,36,15,dark?C.muted:C.gray)}
function label(s,txt,x,y,w=350){t(s,txt,x,y,w,29,16,C.red,{bold:true})}
function para(s,txt,x,y,w,h=110,size=22,color=C.dark){t(s,txt,x,y,w,h,size,color)}
function item(s,n,title,description,x,y,w=535){
  t(s,String(n).padStart(2,'0'),x,y,65,47,25,C.red,{bold:true});
  t(s,title,x+70,y,w-70,45,23,C.dark,{bold:true});
  t(s,description,x+70,y+51,w-72,80,18,C.gray);
}
function table(s,headers,rows,x,y,width,rowH,colWidths){
  const values=[headers,...rows];
  const tab=s.tables.add({rows:values.length,columns:headers.length,left:x,top:y,width,height:rowH*values.length,values,columnWidths:colWidths});
  for(let i=0;i<values.length;i++){
    tab.rows[i].height=rowH;
    for(let j=0;j<headers.length;j++){
      const cell=tab.getCell(i,j);
      cell.fill=i===0?C.dark:(i%2?C.white:C.paper);
      cell.text.style={typeface:FONT,fontSize:i===0?16:17,bold:i===0,color:i===0?C.white:C.dark,
        wrap:'square',verticalAlignment:'middle',insets:{left:12,right:8,top:5,bottom:5}};
    }
  }
  return tab;
}

// 01. Короткое определение продукта.
{
 const s=base('Защита персональных данных\nпри работе с языковой моделью','',['docs/REQUIREMENTS.md'],true);
 t(s,'Наш сервис скрывает сведения о человеке до отправки запроса\nи восстанавливает их в полученном ответе.',66,278,1080,160,30,C.white);
 t(s,'llm-proxy',66,547,420,53,26,C.red,{bold:true});
 foot(s,'Команда Красный Kod  ·  Хакатон АльфаВайб  ·  23 сентября 2026',true);
}
// 02. Пять ключевых пунктов из ТЗ и наблюдаемое состояние.
{
 const s=base('Задача и пять условий успеха','Для каждого требования показываем реализацию и способ проверки.',['docs/REQUIREMENTS.md','README.md']);
 const lines=[
  ['01','Встраивание','Один POST /process без обращения сервиса к модели'],
  ['02','Все категории','Правила для 22 позиций ТЗ; качество свободного текста дорабатывается'],
  ['03','Защита данных','Шифрование временной записи и журналы без исходных значений'],
  ['04','Качество','Тесты и точное восстановление; официальный порог 95% не подтверждён'],
  ['05','Нагрузка','1000 операций/с локально; публичный сервер этот режим не выдержал']
 ];
 lines.forEach((a,i)=>{const y=284+i*68;t(s,a[0],66,y,57,39,23,C.red,{bold:true});t(s,a[1],133,y,234,39,23,C.dark,{bold:true});t(s,a[2],369,y,830,53,19,C.gray)});
}
// 03. Граница ответственности: клиент самостоятельно общается с моделью.
{
 const s=base('Место сервиса в цепочке запросов','Приложение управляет обращением к модели. Наш сервис обрабатывает текст до и после него.',['docs/MASKING.md']);
 const x=[70,365,674,971];
 [['ПРИЛОЖЕНИЕ','Исходный запрос'],['НАШ СЕРВИС','Поиск и замена'],['ПРИЛОЖЕНИЕ','Очищенный текст'],['ЯЗЫКОВАЯ МОДЕЛЬ','Ответ']].forEach((a,i)=>{
  label(s,a[0],x[i],317,260);para(s,a[1],x[i],363,246,90,23);
  if(i<3)t(s,'→',x[i]+263,344,40,50,38,C.red);
 });
 t(s,'Возвращаемся тем же путём',71,514,425,42,25,C.dark,{bold:true});
 para(s,'Приложение передаёт ответ модели нашему сервису с прежним идентификатором.\nСервис восстанавливает известные обозначения.',71,567,1090,80,21);
}
// 04. Архитектура — схема из редактируемых текстовых объектов.
{
 const s=base('Архитектура: приложение и временная память','Одна служба обрабатывает оба направления. Общая временная запись доступна её рабочим процессам.',['docs/ARCHITECTURE.md','docs/DECISIONS.md']);
 const xs=[66,287,537,798,1033], names=['Приложение','HTTP-вход','Правила системы','Поиск и замена','Временная запись'];
 const texts=['Отправляет текст\nи получает ответ','POST /process\nпроверяет формат','Какие категории\nдопустимы','Обнаружение, маска,\nвосстановление','Redis: шифрование\nи срок хранения'];
 names.forEach((name,i)=>{
  label(s,name,xs[i],314,i===4?205:230);
  para(s,texts[i],xs[i],356,i===4?207:213,105,18);
  if(i<4)t(s,'→',xs[i]+205,345,40,56,31,C.red);
 });
 label(s,'Журнал и метрики',66,524,280);
 para(s,'Результат, типы и число найденных данных, длительность этапов. Исходные значения не записываются.',66,563,1080,73,20);
 foot(s,'Redis доступен приложению по внутренней сети; языковую модель вызывает приложение.');
}
// 05. Обоснование стека.
{
 const s=base('Почему этот стек','Для задачи нужны быстрый локальный поиск, короткое хранение соответствий и простой HTTP-интерфейс.',['docs/ARCHITECTURE.md','docs/DECISIONS.md']);
 const rows=[['Python + FastAPI','Правила работы с текстом и проверяемый HTTP-контракт'],
 ['Несколько процессов Uvicorn','Обработка запросов одновременно; число процессов зависит от ресурсов'],
 ['Redis + AES-GCM','Общая временная память, шифрование с проверкой целостности'],
 ['Docker + Prometheus + k6','Повторяемое развёртывание, рабочие показатели и нагрузочные проверки']];
 rows.forEach((a,i)=>{let y=304+i*74;t(s,a[0],67,y,354,51,22,C.dark,{bold:true});para(s,a[1],425,y,758,63,19,C.gray)});
 foot(s,'Поиск не вызывает сторонний сервис. База постоянного хранения и очередь сообщений задачу не упрощают.');
}
// 06. Полный перечень, без обещания качества на неизвестных данных.
{
 const s=base('Какие данные ищем','Правила предусмотрены для всех 22 обязательных позиций ТЗ. Надёжность вне размеченных анкет требует проверки.',['docs/REQUIREMENTS.md','docs/ARCHITECTURE.md','docs/TASK_IMPROVE_PII_DETECTION.md']);
 const groups=[
  ['О человеке','ФИО\nДата рождения\nМесто рождения\nГражданство'],
  ['Документы','Паспорт\nКем выдан\nКод подразделения\nДата выдачи\nВодительские права\nИНН'],
  ['Адрес и связь','Страна · индекс · город\nУлица · дом · квартира\nТелефон\nЭлектронная почта'],
  ['Банковские данные','Номер карты\nЗащитный код CVV\nПИН-код\nИмя держателя']
 ];
 groups.forEach((g,i)=>{const x=66+i*302;label(s,g[0],x,311,274);para(s,g[1],x,355,270,258,20)});
 foot(s,'Наличие правила не означает 100% обнаружения в произвольном тексте; подробный список дан в приложении.');
}
// 07. Детектирование.
{
 const s=base('Как находим сведения о человеке','Сначала получаем кандидатов, затем проверяем их смысл и выбираем точные границы замены.',['docs/MASKING.md','docs/REQUIREMENTS.md']);
 item(s,1,'Форма записи','Телефон, почта, паспорт, карта и ИНН ищутся по виду и контрольным признакам.',65,294,547);
 item(s,2,'Окружающие слова','ФИО, даты, адрес и защитные коды требуют подтверждающего контекста.',663,294,541);
 item(s,3,'Пересечения','Из нескольких находок на одном месте оставляем подходящую по приоритету.',65,457,547);
 item(s,4,'Границы','Замене подлежит найденное значение; соседний текст сохраняется.',663,457,541);
 foot(s,'«Дата рождения: 10.01.1990» требует защиты; обычную дату встречи правило не должно принимать за неё.');
}
// 08. Маскирование.
{
 const s=base('Как создаётся маска','Пример с вымышленными данными. Одно и то же значение получает одну маску внутри запроса.',['docs/MASKING.md']);
 label(s,'Исходный текст',67,288);para(s,'Напишите на ivan@example.com. Позвоните +7 916 123-45-67.\nПовторите письмо на ivan@example.com.',67,328,1114,116,24);
 label(s,'После обработки',67,477);para(s,'Напишите на <EMAIL_1>. Позвоните <PHONE_2>.\nПовторите письмо на <EMAIL_1>.',67,517,1114,91,25,C.dark);
 foot(s,'Соответствие шифруется и хранится временно; замены в тексте применяются справа налево.');
}
// 09. Два сценария восстановления.
{
 const s=base('Два способа восстановить данные','Оба работают через POST /process с тем же идентификатором запроса.',['docs/MASKING.md','docs/REQUIREMENTS.md']);
 label(s,'А. Ранее выданная маска',66,300,530);para(s,'Передали замаскированную строку без изменений. Сервис вернёт исходный запрос посимвольно.',66,349,534,116,23);
 label(s,'Б. Новый ответ модели',663,300,530);para(s,'«Письмо отправьте на <EMAIL_1>» превращается в «Письмо отправьте на ivan@example.com».',663,349,518,155,23);
 para(s,'Неизвестные или изменённые моделью обозначения остаются в тексте. Соответствия из другого запроса или другой системы не используются.',66,559,1102,74,19,C.gray);
}
// 10. Контракт и политики.
{
 const s=base('Подключение и настройки систем','Запрос содержит ровно два поля. Ответ содержит только обработанный текст.',['docs/REQUIREMENTS.md','config/systems.example.yaml','README.md']);
 label(s,'HTTP-интерфейс',67,285,500);
 para(s,'POST /process\n{ "payload": "...", "payload_id": "..." }\n{ "result": "..." }',67,330,570,145,23);
 label(s,'Настройки для приложения',675,285,516);
 para(s,'Включено ли подключение\nКакие категории данных защищать\nРазрешено ли восстановление\nКак выглядит обозначение',675,330,514,200,21);
 foot(s,'Сейчас активную систему выбирают при развёртывании. Публичный вызов не удостоверяет отправителя.');
}
// 11. Защита и срок хранения.
{
 const s=base('Что защищает временную запись','Без соответствий между масками и значениями восстановление было бы невозможно.',['docs/ARCHITECTURE.md','docs/MASKING.md','docs/DEPLOYMENT_RAILWAY.md']);
 t(s,'15 минут',68,293,410,80,44,C.red,{bold:true});para(s,'Срок хранения после маскирования',68,366,470,68,21);
 t(s,'2 минуты',681,293,460,80,44,C.red,{bold:true});para(s,'Срок после успешного восстановления',681,366,503,68,21);
 para(s,'Запись зашифрована AES-GCM. Ключ задаётся отдельно от кода. Redis не опубликован в интернете. В журнал не попадают исходный текст и значения найденных данных.',68,506,1080,112,21);
 foot(s,'Сроки задаются конфигурацией. Полное соответствие внутренним правилам ИБ банка отдельно не подтверждалось.');
}
// 12. Наблюдаемость.
{
 const s=base('Журналы и рабочие показатели','По запросу сохраняются безопасные признаки обработки; /metrics отдаёт агрегированные счётчики и задержки.',['docs/ARCHITECTURE.md','src/llm_proxy/observability/metrics.py','src/llm_proxy/observability/logging.py']);
 label(s,'Одна запись в журнале',66,294,500);
 para(s,'Операция: маскирование\nКод ответа: 200\nНайденные типы: email, phone\nЧисло находок: 3\nПоиск: 6,1 мс · Redis: 1,2 мс',66,338,508,210,20);
 label(s,'Что можно измерить',658,294,530);
 para(s,'Запросы в секунду и время ответа\nОтказы, перегрузка и занятые процессы\nЧисло находок по категориям\nСкорость обработки текста и время Redis',658,338,520,210,20);
 foot(s,'Текстовые единицы считаются по пробелам: это не токены конкретной языковой модели.');
}
// 13. Оценка качества — честные границы.
{
 const s=base('Что показывают проверки качества','Внутренние тесты и официальная проверка используют разные данные и не заменяют друг друга.',['README.md','docs/REQUIREMENTS.md','docs/TASK_IMPROVE_PII_DETECTION.md','scripts/eval_labeled_sample.py','tests/test_questionnaire_detection.py','https://github.com/rp-alpha-vibe/llm-proxy/commit/73153457f2b6aba31b61d933b45636d56ee961ee']);
 t(s,'4 400 / 4 400',68,290,600,103,45,C.red,{bold:true});para(s,'заявленное покрытие размеченных полей\nв 200 синтетических анкетах',68,380,560,85,20);
 t(s,'F1 = 1,0',703,290,472,103,46,C.red,{bold:true});para(s,'старый локальный набор из 46 примеров',703,379,460,63,20);
 para(s,'Проверяем типы и границы, лишние срабатывания, маску и восстановление. Поиск данных в свободных формулировках исправляется и проходит отдельную регрессию; результат по анкетам не доказывает его качество.',68,487,1110,117,21);
 foot(s,'Порог 95% на неизвестных данных организаторов пока не подтверждён.');
}
// 14. Reliability.
{
 const s=base('Поведение при ошибках и большой нагрузке','Сервис не отдаёт исходные данные как запасной путь при сбое временной памяти.',['docs/MASKING.md','docs/ARCHITECTURE.md','docs/REQUIREMENTS.md']);
 item(s,1,'Некорректный запрос','HTTP 422 без вывода исходного текста в журнал.',66,292,556);
 item(s,2,'Перегрузка','HTTP 429 с указанием времени до повтора.',664,292,540);
 item(s,3,'Проблема Redis','Контролируемая ошибка 503; обработка закрывается.',66,468,556);
 item(s,4,'Повтор запроса','Прежняя маска возвращается по тому же идентификатору.',664,468,540);
 foot(s,'Ограничение 8 млн символов; 100 тыс. условных токенов тестировались локально отдельно.');
}
// 15. Evidence performance.
{
 const s=base('Скорость зависит от среды запуска','Пятиминутный профиль 1000 операций в секунду: полный локальный прогон прошёл, публичный нет.',['docs/ARCHITECTURE.md','submission/railway-load-probe-2026-09-23.md']);
 table(s,['Показатель','Локальный компьютер','Railway'],[
  ['Успешно за 300 с','300 001','193 444'],
  ['Успешно в секунду','≈1000','≈645'],
  ['Время ответа p95','21,78 мс','≈10 с'],
  ['Ошибки','0','≈33%']
 ],66,284,1146,58,[423,353,370]);
 foot(s,'Короткий прогон Railway: 100 операций/с, 30 с, без ошибок. Локально: 8 процессов; в Railway ресурс ограничен.');
}
// 16. Additional work.
{
 const s=base('Дополнительные возможности: фактическое состояние','Бонусные пункты показываем отдельно от обязательных требований.',['docs/REQUIREMENTS.md','docs/ARCHITECTURE.md','config/systems.example.yaml']);
 const rows=[
  ['Два формата обозначений для систем','Реализовано'],
  ['Новые типы через дополнительные правила','Предусмотрено в устройстве'],
  ['Отдельная токенизация / синтетические значения','Не реализованы'],
  ['2000 операций/с до 1 секунды','Не подтверждено'],
  ['Новые виды удостоверений и составные правила','Не подтверждены']
 ];
 rows.forEach((r,i)=>{let y=294+i*68;para(s,r[0],68,y,800,55,21);t(s,r[1],888,y,294,55,19,i<2?C.dark:C.red,{bold:true})});
}
// 17. Requirement traceability.
{
 const s=base('Сводка по требованиям','Состояние отражает проверки команды на момент подготовки материалов.',['docs/REQUIREMENTS.md','README.md','submission/railway-load-probe-2026-09-23.md']);
 table(s,['Требование','Что сделано','Что подтверждено'],[
  ['Интерфейс и восстановление','POST /process, два сценария','Локальные и сквозные проверки'],
  ['22 категории данных','Правила предусмотрены','Качество на неизвестных данных открыто'],
  ['Разные системы и доступ','Политики из конфигурации','Публичная авторизация отсутствует'],
  ['Журналы и защита','Метрики, шифрование, срок','Локальные тесты и проверка среды'],
  ['95% качества','Внутренний набор пройден','Официальный прогон открыт'],
  ['1000 операций/с','Достигнуто локально','Railway не прошёл']
 ],66,275,1147,53,[270,402,475]);
}
// 18. Demo and conclusion.
{
 const s=base('Демонстрация и материалы','Запрос с вымышленными данными доступен через публичный адрес.',['README.md','submission/CHECKLIST.md']);
 label(s,'Публичный адрес',66,290,470);
 link(s,'https://llm-proxy-production-84c7.up.railway.app',
   'https://llm-proxy-production-84c7.up.railway.app',66,331,1110,73,25);
 label(s,'Исходный код',66,436,470);
 link(s,'https://github.com/rp-alpha-vibe/llm-proxy',
   'https://github.com/rp-alpha-vibe/llm-proxy',66,477,1050,66,25);
 para(s,'Открытые проверки: официальный результат качества и допуск тестера. Нагрузочный профиль на публичном сервере пока не пройден.',66,567,1100,76,20,C.gray);
 foot(s,'Публичная демонстрация предназначена только для вымышленных данных.');
}
// 19. Appendix complete checklist.
{
 const s=base('Приложение: все 22 категории','Каждая строка адреса из задания учитывается отдельно.',['docs/REQUIREMENTS.md']);
 const colA=['1 ФИО','2 Дата рождения','3 Место рождения','4 Гражданство','5 Паспорт','6 Орган выдачи','7 Код подразделения','8 Дата выдачи'];
 const colB=['9 Водительское удостоверение','10 ИНН','11 Страна','12 Индекс','13 Город','14 Улица','15 Дом','16 Квартира'];
 const colC=['17 Телефон','18 Электронная почта','19 Номер карты','20 CVV','21 ПИН-код','22 Имя держателя карты'];
 [colA,colB,colC].forEach((arr,i)=>para(s,arr.join('\n'),66+i*399,295,380,320,21));
 foot(s,'Правила предусмотрены для всех позиций; общая доля корректного обнаружения требует отдельной проверки.');
}
// 20. Appendix configuration and caveat.
{
 const s=base('Приложение: настройка нового приложения','Добавление типового потребителя не требует менять алгоритм поиска.',['README.md','config/systems.example.yaml','docs/ARCHITECTURE.md']);
 para(s,'1. Добавить систему в config/systems.example.yaml.\n2. Указать enabled и список защищаемых категорий.\n3. Разрешить либо запретить восстановление.\n4. Выбрать формат обозначений.\n5. Установить идентификатор активной системы при запуске.',66,296,1110,277,23);
 foot(s,'Отдельную проверку личности вызывающего приложения текущий публичный интерфейс не выполняет.');
}
// 21. Appendix test protocol.
{
 const s=base('Приложение: как измеряли нагрузку','Сравнивать среды можно только вместе с условиями испытаний.',['docs/REQUIREMENTS.md','docs/ARCHITECTURE.md','submission/railway-load-probe-2026-09-23.md']);
 para(s,'Профиль: 300 секунд после прогрева, целевая подача 1000 операций/с. Одна операция означает отдельное маскирование или восстановление. Успешный повтор не скрывает ошибку предыдущей попытки.',66,285,1090,123,21);
 label(s,'Локальный компьютер',66,455,520);para(s,'8 рабочих процессов; 300 001 успешная операция; ошибок и 429 нет.',66,493,515,109,21);
 label(s,'Публичный Railway',662,455,520);para(s,'193 444 успешных операций; 76 483 ответа 429; 10 019 пропущенных итераций.',662,493,536,109,21);
 foot(s,'Подробные условия и первичные метрики k6 находятся в submission/railway-load-probe-2026-09-23.md.');
}

await fs.mkdir(TMP_DIR,{recursive:true});
await fs.mkdir(path.dirname(FINAL_PPTX),{recursive:true});
const candidate=path.join(TMP_DIR,'presentation-candidate.pptx');
await (await PresentationFile.exportPptx(P)).save(candidate);
const receipt=path.join(TMP_DIR,`${path.basename(FINAL_PPTX)}.validation.json`);
const result=await finalizePresentation({
  workspaceDir:path.dirname(TMP_DIR),candidatePath:candidate,finalPath:FINAL_PPTX,
  pythonExecutable:RUNTIME_PYTHON,
  integrityValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit',
    '--require-native-table-slide','15','--require-native-table-slide','17'],
  requiredNativeTableOwnerSlides:[15,17],
  fontPolicy:{basis:'design',families:[FONT]},
  verifyArtifactToolImport:true,receiptPath:receipt,
});
console.log(JSON.stringify({slides:slideNo,candidate,final:FINAL_PPTX,result}));
