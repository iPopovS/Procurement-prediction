// Small, dependency-free UI dictionary. API values and source documents stay unchanged.
const STORAGE_KEY = 'tender-predictor-language';
const supported = ['ru', 'en'];
let language = 'ru';
try {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (supported.includes(saved)) language = saved;
} catch { /* Storage can be disabled; Russian is still the default. */ }

export const translations = {
  'Tender Price Predictor': 'Прогноз цены закупки',
  'Interface language': 'Язык интерфейса',
  'Search by number, title, organizer, code or address': 'Поиск по номеру, названию, организатору, коду или адресу',
  'Search tenders': 'Поиск закупок',
  'Prediction model status': 'Состояние модели прогнозирования',
  'Model loading': 'Модель загружается',
  'Model ready': 'Модель готова',
  'Model unavailable': 'Модель недоступна',
  'Filters': 'Фильтры',
  'Upload tenders': 'Загрузить закупки',
  'Status': 'Статус',
  'Purchase type': 'Способ закупки',
  'Region': 'Регион',
  'Find a region': 'Найти регион',
  'Organizer': 'Организатор',
  'Name or ID': 'Название или идентификатор',
  'Published': 'Дата публикации',
  'From': 'С',
  'To': 'По',
  'Max price, RUB': 'Начальная цена, ₽',
  'Min': 'От',
  'Max': 'До',
  'Location': 'Местоположение',
  'Any': 'Любое',
  'Shown on the map': 'На карте',
  'Not on the map': 'Не на карте',
  'Reset all filters': 'Сбросить все фильтры',
  'Map of tenders': 'Карта закупок',
  'Updating map…': 'Обновление карты…',
  'Tender details': 'Информация о закупке',
  'This application needs JavaScript.': 'Для работы приложения необходим JavaScript.',
  'Legend and layers': 'Легенда и слои',
  'Hide legend': 'Скрыть легенду',
  'Colour by': 'Цвет маркеров',
  'Colour markers by': 'Выбор цвета маркеров',
  'Size = number of tenders': 'Размер — количество закупок',
  'Country and region borders': 'Границы стран и регионов',
  'Fit map to tenders': 'Показать все закупки на карте',
  'Winner price known': 'Цена победителя известна',
  'Predicted, no winner yet': 'Есть прогноз, победитель ещё не известен',
  'Not predicted yet': 'Прогноз ещё не рассчитан',
  'Has winner price': 'Есть цена победителя',
  'Has prediction': 'Есть прогноз',
  'No prediction yet': 'Нет прогноза',
  'All tenders': 'Все закупки',
  'EF': 'Электронный аукцион',
  'EZK': 'Электронный запрос котировок',
  'EZT': 'Электронный запрос предложений',
  'No data yet.': 'Данных пока нет.',
  'Data range: {min} to {max}': 'Диапазон данных: от {min} до {max}',
  'Tenders without a region: {n}': 'Закупок без региона: {n}',
  'No organizer matches.': 'Организаторы не найдены.',
  'Remove organizer filter': 'Убрать фильтр по организатору',
  'Tenders: {n}': 'Закупок: {n}',
  'Matching tenders: {n} of {total}': 'По фильтрам: {n} из {total} закупок',
  'with winner': 'с ценой победителя',
  'predicted': 'с прогнозом',
  'pending': 'без прогноза',
  'not on map': 'не на карте',
  'Listed and searchable, but without a map location': 'Доступны в поиске, но местоположение на карте не определено',
  'RUB': '₽',
  'No tenders yet': 'Закупок пока нет',
  'Upload purchase numbers and they are fetched from GosPlan, stored and drawn on the map.': 'Загрузите номера закупок: приложение получит данные из ГосПлана, сохранит их и покажет на карте.',
  'No tenders match these filters': 'По этим фильтрам закупки не найдены',
  'Try removing a filter or widening the date or price range.': 'Уберите часть фильтров или расширьте диапазон дат или цен.',
  'These tenders have no map location': 'Местоположение этих закупок не определено',
  'They are still listed in search and can be opened from there. Locations come from the region code in the GosPlan record.': 'Закупки доступны в поиске — оттуда можно открыть их карточки. Местоположение определяется по коду региона в данных ГосПлана.',
  '(legacy file)': '(старый формат файла)',
  'Model {version}; history covers purchases finished until {date}': 'Модель {version}; история завершённых закупок по {date}',
  'Library version warnings': 'Предупреждения о версиях библиотек',
  'The model loads in the background after start-up (about a minute).': 'Модель загружается в фоновом режиме после запуска (около минуты).',
  'The application could not start: {error}': 'Не удалось запустить приложение: {error}',
  'Searching…': 'Поиск…',
  'No tenders match “{q}”. Check the spelling or clear the filters.': 'По запросу «{q}» ничего не найдено. Проверьте написание или сбросьте фильтры.',
  'No title': 'Без названия',
  'No region': 'Регион не указан',
  'Showing {n} of {total} matches. Keep typing to narrow down.': 'Показано {n} из {total} результатов. Уточните запрос.',
  'Matches: {n}': 'Найдено: {n}',
  'Loading…': 'Загрузка…',
  'Loading tenders…': 'Загрузка закупок…',
  'Exact coordinates are not available; the point is the centre of the region.': 'Точные координаты отсутствуют; точка обозначает центр региона.',
  'Approximate location': 'Приблизительное местоположение',
  'Exact location': 'Точное местоположение',
  'No map location': 'Местоположение не определено',
  'No tenders at this location match your search.': 'В этом месте нет закупок по вашему запросу.',
  'No tenders here.': 'Здесь нет закупок.',
  'Show more ({n} left)': 'Показать ещё (осталось {n})',
  'this location': 'это место',
  '{n} tenders — {region}': 'Закупок: {n} — {region}',
  'Search within these tenders': 'Поиск среди этих закупок',
  'Close panel': 'Закрыть панель',
  'The maximum price is not available for this tender.': 'Начальная цена этой закупки не указана.',
  'Predicted price, {discount} below the max price of {max}': 'Прогноз цены: на {discount} ниже начальной цены {max}',
  'Winner price, {discount} below the max price of {max}': 'Цена победителя: на {discount} ниже начальной цены {max}',
  'Max price. No prediction has been generated yet.': 'Начальная цена. Прогноз ещё не рассчитан.',
  'Predicted': 'Прогноз',
  'Winner': 'Победитель',
  'Price scale from zero to the maximum price': 'Шкала цены от нуля до начальной цены',
  'Max price': 'Начальная цена',
  'Prediction unavailable.': 'Прогноз недоступен.',
  'Try again': 'Попробовать снова',
  'Generate price prediction': 'Рассчитать прогноз цены',
  'Uses only what was known when the notice was published.': 'Используются только сведения, известные на момент публикации извещения.',
  'Very low price (under 1% of max, usually per-unit pricing)': 'Очень низкая цена (менее 1% начальной, обычно цена за единицу)',
  'Partial price drop': 'Частичное снижение цены',
  'No drop (ends at the max price)': 'Без снижения (итог равен начальной цене)',
  'Compared with the winner price, the prediction was': 'По сравнению с ценой победителя прогноз оказался',
  'too high': 'завышен',
  'too low': 'занижен',
  'of the winner price': 'от цены победителя',
  'of the max price': 'от начальной цены',
  'Take with care': 'Учитывайте ограничения',
  'a very low final price': 'очень низкая итоговая цена',
  'a partial price drop': 'частичное снижение цены',
  'no price drop': 'отсутствие снижения цены',
  'How the model sees it': 'Оценка модели',
  'Most likely outcome': 'Наиболее вероятный исход',
  'Outcome probabilities': 'Вероятности исходов',
  'For totals': 'Для суммирования',
  'Mean estimate. Use this, not the figure above, when adding up many tenders.': 'Средняя оценка. При суммировании нескольких закупок используйте её, а не значение выше.',
  'Typical error': 'Типичная ошибка',
  'About {pct} of the max price ({price}) per tender, on average.': 'В среднем около {pct} начальной цены ({price}) на закупку.',
  'Reference value from the model documentation, not a confidence interval.': 'Справочное значение из документации модели, не доверительный интервал.',
  'History used': 'Использованная история',
  '{n} earlier finished purchases by this organizer. Of those, {g2} share the purchase type and product group (first 2 characters of the code) and {g5} the narrower group (first 5 characters).': 'Завершённых ранее закупок этого организатора: {n}. Из них {g2} совпадают по способу закупки и группе товаров (первые 2 знака кода), а {g5} — по более узкой группе (первые 5 знаков).',
  'Regenerate prediction': 'Пересчитать прогноз',
  'No winner price on record.': 'Цена победителя пока неизвестна.',
  'Check the protocols again': 'Проверить протоколы ещё раз',
  'provided with the uploaded record': 'указана в загруженной записи',
  'taken from the protocol published {date}': 'получена из протокола, опубликованного {date}',
  'taken from the protocols': 'получена из протоколов',
  'Winner price': 'Цена победителя',
  'below the max price': 'ниже начальной цены',
  'Shown for reference only; the model never sees it.': 'Показана только для справки; модель не использует её в прогнозе.',
  'All {n} tenders — {region}': 'Все закупки ({n}) — {region}',
  'about': 'около',
  'Title taken from the notice document.': 'Название взято из документа извещения.',
  'No title available': 'Название отсутствует',
  'Download the GosPlan JSON for this purchase': 'Скачать данные этой закупки из ГосПлана в формате JSON',
  'Download GosPlan data for purchase {pn}': 'Скачать данные закупки {pn} из ГосПлана',
  'Price': 'Цена',
  'Details': 'Сведения',
  'Bids due': 'Окончание подачи заявок',
  'Contract guarantee': 'Обеспечение контракта',
  'KTRU codes': 'Коды КТРУ',
  'OKPD2 codes': 'Коды ОКПД2',
  'Positions': 'Количество позиций',
  'Plan numbers': 'Номера планов',
  'IKZ': 'ИКЗ',
  'Trading platform': 'Электронная площадка',
  'Official notice': 'Официальное извещение',
  'Open on zakupki.gov.ru': 'Открыть на zakupki.gov.ru',
  'Updated at source': 'Обновлено в источнике',
  'Stored in this app': 'Обновлено в приложении',
  'Generating…': 'Расчёт…',
  'No winner price has been published yet.': 'Цена победителя ещё не опубликована.',
  'GosPlan could not deliver this purchase (HTTP {status}).': 'Не удалось получить закупку из ГосПлана (HTTP {status}).',
  '{n} tenders in a group of locations': 'Закупок в группе местоположений: {n}',
  '{n} tenders in {locations} locations': 'Закупок: {n}; местоположений: {locations}',
  'and {n} more': 'и ещё {n}',
  'Click to zoom in.': 'Нажмите, чтобы приблизить.',
  'Approximate location (region centre)': 'Приблизительное местоположение (центр региона)',
  'Largest {n} by max price. Click to browse all.': 'Показаны {n} закупки с наибольшей начальной ценой. Нажмите, чтобы увидеть все.',
  'Zoom in': 'Приблизить',
  'Zoom out': 'Отдалить',
  'Toggle attribution': 'Показать или скрыть сведения об источниках карты',
  'Map': 'Карта',
  'Map marker': 'Маркер карты',
  'Close popup': 'Закрыть подсказку',
  'Close': 'Закрыть',
  'Paste purchase numbers, separated by spaces, commas or new lines.': 'Вставьте номера закупок через пробел, запятую или с новой строки.',
  'or drop a CSV, TXT or JSON file here': 'или перетащите сюда файл CSV, TXT или JSON',
  'Choose a file': 'Выбрать файл',
  'Predict prices immediately': 'Сразу рассчитать прогноз цен',
  'Look up winner prices (display only, one extra request per tender)': 'Получить цены победителей (для справки; один дополнительный запрос на закупку)',
  'Skip purchase numbers that are already stored': 'Пропускать уже сохранённые закупки',
  'Upload': 'Загрузить',
  'Items ready: {n}': 'Готово к загрузке: {n}',
  'An upload is still running. Close anyway? It will continue in the background.': 'Загрузка ещё идёт. Закрыть окно? Загрузка продолжится в фоновом режиме.',
  '{file}: loaded purchase numbers: {numbers}; full records: {records}.': '{file}: загружено номеров закупок: {numbers}; полных записей: {records}.',
  '{file} is not valid JSON.': 'Файл {file} содержит некорректный JSON.',
  'Add at least one purchase number first.': 'Сначала добавьте хотя бы один номер закупки.',
  '(record)': '(запись)',
  'Processed {done} of {total}': 'Обработано {done} из {total}',
  'Finished: {n} items processed.': 'Готово. Обработано записей: {n}.',
  'stored': 'сохранено',
  'skipped': 'пропущено',
  'failed': 'с ошибкой',
  'with winner price': 'с ценой победителя',
  'not predictable': 'прогноз недоступен',
  'Added': 'Добавлено',
  'Updated': 'Обновлено',
  'Skipped': 'Пропущено',
  'Failed': 'Ошибка',
  'below max': 'ниже начальной цены',
  'Result': 'Результат',
  'Show only failed items': 'Показать только записи с ошибками',
  'Purchase number': 'Номер закупки',
  'Prediction': 'Прогноз',
  'Note': 'Примечание',
  'Cannot reach the server. Check your connection and try again.': 'Нет связи с сервером. Проверьте подключение и попробуйте снова.',
  'The server answered with an error (HTTP {status}).': 'Сервер вернул ошибку (HTTP {status}).',
  'Region {code}': 'Регион {code}',
  'The purchase type is missing in the GosPlan record.': 'В данных ГосПлана не указан способ закупки.',
  'The maximum price (max_price) is missing or not a number.': 'Начальная цена (max_price) отсутствует или не является числом.',
  'The maximum price must be greater than 1 RUB.': 'Начальная цена должна быть больше 1 рубля.',
  'The publication date is missing or unreadable. The model needs it to look up organizer history without leaking future information.': 'Дата публикации отсутствует или не распознана. Она нужна модели для поиска истории организатора без использования будущих данных.',
  'The model is still loading (this takes 1-2 minutes after start). Try again shortly.': 'Модель ещё загружается (1–2 минуты после запуска). Попробуйте чуть позже.',
  'The model is still loading (1-2 minutes after start). Try again shortly.': 'Модель ещё загружается (1–2 минуты после запуска). Попробуйте чуть позже.',
  'The model is not loaded.': 'Модель не загружена.',
  'The model returned a non-finite value for this tender.': 'Модель вернула некорректное числовое значение для этой закупки.',
  'No result.': 'Результат отсутствует.',
  'Organizer ID is missing, so organizer history was not used (global averages applied).': 'Идентификатор организатора отсутствует, поэтому его история не использована (применены общие средние значения).',
  "No earlier finished purchases from this organizer were found in the model's history; global averages were used for the organizer signal.": 'В истории модели нет ранее завершённых закупок этого организатора; использованы общие средние значения.',
  'No OKPD2/KTRU codes: product-group history could not be used.': 'Коды ОКПД2/КТРУ отсутствуют: история по группе товаров не использована.',
  'The object description is empty, so text signals were not available.': 'Описание объекта закупки отсутствует, поэтому текстовые признаки недоступны.',
  'GosPlan did not answer in time': 'ГосПлан не ответил вовремя',
  'GosPlan returned a response that is not valid JSON': 'ГосПлан вернул некорректный JSON',
  'GosPlan response has no purchase_number': 'В ответе ГосПлана отсутствует номер закупки (purchase_number)',
  'Protocols response is not a list': 'Ответ с протоколами имеет неверный формат',
  'This purchase number is not stored. Upload it first.': 'Эта закупка ещё не сохранена. Сначала загрузите её.',
  'Unexpected server error. Check the server log.': 'Непредвиденная ошибка сервера. Проверьте журнал сервера.',
  'Provide `purchase_numbers` and/or `records`.': 'Укажите номера закупок (purchase_numbers) или полные записи (records).',
  'File is larger than 20 MB.': 'Размер файла превышает 20 МБ.',
  'No purchase numbers found in the file.': 'В файле не найдены номера закупок.',
  'The record has no valid purchase_number.': 'В записи отсутствует корректный номер закупки (purchase_number).',
  'Not a valid purchase number (expected 8-25 digits).': 'Некорректный номер закупки (ожидается от 8 до 25 цифр).',
  'already stored': 'уже сохранена',
  'no protocols published yet': 'протоколы ещё не опубликованы',
  'no results protocol among the published documents': 'среди опубликованных документов нет итогового протокола',
  'no valid winner price found': 'корректная цена победителя не найдена',
  'protocol has no applications': 'в протоколе нет заявок',
  'single application without rating': 'единственная заявка без рейтинга',
  'no application ratings; lowest price used': 'рейтинги заявок отсутствуют; использована минимальная цена',
  'preliminary: taken from the submit-offers protocol': 'предварительная цена: получена из протокола подачи ценовых предложений',
  'max_price unknown; winner price cannot be validated': 'начальная цена неизвестна; проверить цену победителя невозможно',
  'not a number': 'не является числом',
  'Purchase type {type} is not supported by the model (supported: {types}).': 'Способ закупки {type} не поддерживается моделью (поддерживаются: {types}).',
  'The model failed to load: {error}': 'Не удалось загрузить модель: {error}',
  'The model is not available: {error}': 'Модель недоступна: {error}',
  'Prediction failed unexpectedly ({error}).': 'Непредвиденная ошибка расчёта прогноза ({error}).',
  "The model's history ends on {date}; this tender was published later, so recent organizer behavior is not reflected.": 'История модели заканчивается {date}; закупка опубликована позже, поэтому последние действия организатора не учтены.',
  'Currency is {currency}; the model was trained on RUB prices.': 'Валюта закупки — {currency}; модель обучена на ценах в рублях.',
  'Could not reach GosPlan ({error})': 'Не удалось связаться с ГосПланом ({error})',
  'Not found in GosPlan (HTTP {status})': 'Не найдено в ГосПлане (HTTP {status})',
  'GosPlan is unavailable (HTTP {status})': 'ГосПлан недоступен (HTTP {status})',
  'GosPlan returned HTTP {status}': 'ГосПлан вернул HTTP {status}',
  'Could not read the record ({error}).': 'Не удалось прочитать запись ({error}).',
  'At most {n} items per request; send the rest in further requests.': 'Не более {n} записей за запрос; отправьте остальные отдельными запросами.',
  'winner lookup failed: {error}': 'не удалось получить цену победителя: {error}',
  'uploaded winner_price ignored: {error}': 'загруженная цена победителя проигнорирована: {error}',
  'winner price {price} is not positive': 'цена победителя {price} должна быть положительной',
  'winner price {price} exceeds max price {max}': 'цена победителя {price} превышает начальную цену {max}',
  '{library}: model was trained with {trained}, installed {installed}': '{library}: модель обучена с версией {trained}, установлена {installed}',
  'Model files failed verification: {error}': 'Файлы модели не прошли проверку: {error}',
  'file is missing': 'файл отсутствует',
  'not listed in manifest.json': 'не указан в manifest.json',
  'checksum mismatch (incomplete download or modified file)': 'контрольная сумма не совпадает (неполная загрузка или изменённый файл)',
};

export const getLanguage = () => language;
export const getLocale = () => language === 'ru' ? 'ru-RU' : 'en-US';
const listeners = new Set();
export function onLanguageChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

export function t(key, values = {}) {
  const text = language === 'ru' ? translations[key] ?? key : key;
  return text.replace(/\{(\w+)\}/g, (match, name) => String(values[name] ?? match));
}

export function setLanguage(next) {
  if (!supported.includes(next) || next === language) return;
  language = next;
  try { localStorage.setItem(STORAGE_KEY, next); } catch { /* Memory-only preference. */ }
  translateDOM();
  listeners.forEach((fn) => fn(next));
}

// Only explicitly marked interface text is translated, never tender titles/addresses.
export function translateDOM(root = document) {
  if (root === document) document.documentElement.lang = language;
  root.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  for (const attr of ['placeholder', 'title', 'aria-label']) {
    root.querySelectorAll(`[data-i18n-${attr}]`).forEach((el) => {
      el.setAttribute(attr, t(el.getAttribute(`data-i18n-${attr}`)));
    });
  }
  document.querySelectorAll('[data-language]').forEach((el) => {
    el.setAttribute('aria-pressed', String(el.dataset.language === language));
  });
}

export function initLanguage() {
  translateDOM();
  document.querySelectorAll('[data-language]').forEach((el) => {
    el.addEventListener('click', () => setLanguage(el.dataset.language));
  });
}

let regions = {};
let regionCodes = new Map();
export function setRegions(table) {
  regions = table;
  regionCodes = new Map(Object.entries(table).flatMap(([code, r]) => [[r.name_en, code], [r.name_ru, code]]));
}
export function regionName(codeOrName, fallback = '') {
  const code = regionCodes.get(codeOrName) || String(codeOrName ?? '').padStart(2, '0');
  const region = regions[code];
  if (region) return region[language === 'ru' ? 'name_ru' : 'name_en'];
  const unknown = /^Region (\d+)$/.exec(String(codeOrName));
  if (unknown) return t('Region {code}', { code: unknown[1] });
  if (/^\d+$/.test(String(codeOrName))) return t('Region {code}', { code });
  return fallback || codeOrName || '';
}

// Translate service-owned messages, including ones already saved in SQLite. Unknown
// diagnostics are kept verbatim rather than hiding useful technical information.
const messagePatterns = [
  [/^The server answered with an error \(HTTP (\d+)\)\.$/, 'The server answered with an error (HTTP {status}).', ['status']],
  [/^(.+): model was trained with (.+), installed (.+)$/, '{library}: model was trained with {trained}, installed {installed}', ['library', 'trained', 'installed']],
  [/^Model files failed verification: (.+)$/s, 'Model files failed verification: {error}', ['error']],
  [/^Purchase type (.+) is not supported by the model \(supported: (.+)\)\.$/, 'Purchase type {type} is not supported by the model (supported: {types}).', ['type', 'types']],
  [/^The model failed to load: (.+)$/s, 'The model failed to load: {error}', ['error']],
  [/^The model is not available: (.+)$/s, 'The model is not available: {error}', ['error']],
  [/^Prediction failed unexpectedly \((.+)\)\.$/, 'Prediction failed unexpectedly ({error}).', ['error']],
  [/^The model's history ends on (.+); this tender was published later, so recent organizer behavior is not reflected\.$/, "The model's history ends on {date}; this tender was published later, so recent organizer behavior is not reflected.", ['date']],
  [/^Currency is (.+); the model was trained on RUB prices\.$/, 'Currency is {currency}; the model was trained on RUB prices.', ['currency']],
  [/^Could not reach GosPlan \((.+)\)$/, 'Could not reach GosPlan ({error})', ['error']],
  [/^Not found in GosPlan \(HTTP (\d+)\)$/, 'Not found in GosPlan (HTTP {status})', ['status']],
  [/^GosPlan is unavailable \(HTTP (\d+)\)$/, 'GosPlan is unavailable (HTTP {status})', ['status']],
  [/^GosPlan returned HTTP (\d+)$/, 'GosPlan returned HTTP {status}', ['status']],
  [/^Could not read the record \((.+)\)\.$/, 'Could not read the record ({error}).', ['error']],
  [/^At most (\d+) items per request; send the rest in further requests\.$/, 'At most {n} items per request; send the rest in further requests.', ['n']],
  [/^winner lookup failed: (.+)$/s, 'winner lookup failed: {error}', ['error']],
  [/^uploaded winner_price ignored: (.+)$/s, 'uploaded winner_price ignored: {error}', ['error']],
  [/^winner price (.+) is not positive$/, 'winner price {price} is not positive', ['price']],
  [/^winner price (.+) exceeds max price (.+)$/, 'winner price {price} exceeds max price {max}', ['price', 'max']],
];

export function translateMessage(message) {
  if (message == null) return '';
  const text = String(message);
  if (language === 'en') return text;
  if (Object.hasOwn(translations, text)) return t(text);
  for (const [pattern, key, names] of messagePatterns) {
    const match = pattern.exec(text);
    if (match) return t(key, Object.fromEntries(names.map((name, i) => [name, name === 'error' ? translateMessage(match[i + 1]) : match[i + 1]])));
  }
  // Protocol diagnostics can contain a document type prefix and several caveats.
  const protocol = /^(epProtocol\w+): (.+)$/s.exec(text);
  if (protocol) return `${protocol[1]}: ${translateMessage(protocol[2])}`;
  if (text.includes('; ')) return text.split('; ').map(translateMessage).join('; ');
  return text;
}