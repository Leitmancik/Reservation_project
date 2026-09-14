/**
 * Přijímá rezervace z aplikace a zapisuje je do téhle tabulky.
 *
 * Nasazení: Rozšíření → Apps Script → vložit tenhle kód →
 * Nasadit → Nová implementace → typ "Webová aplikace" →
 * Spustit jako "Já", Přístup "Kdokoli" → zkopírovat URL.
 *
 * Požadavky přijímáme přes GET i POST. Některé domény Google Workspace
 * POST na webovou aplikaci neprotlačí (vrátí 405), proto aplikace
 * standardně posílá data v parametru "payload" metodou GET.
 *
 * TOKEN níž musí být stejný jako v nastavení aplikace. Slouží jako
 * heslo — adresa webové aplikace je totiž veřejná, takže bez něj by
 * do tabulky mohl psát kdokoli, kdo ji zná.
 */

const TOKEN = 'SEM_VLOZ_TOKEN';

const HEADER = [
  'Jméno',
  'Příjmení',
  'email',
  'Datum - Start',
  'Datum - Konec',
  'Stav',
  'ID',
  'Vytvořeno',
];

const COL_ID = 7;
const COL_STATUS = 6;

function doGet(e) {
  return handle(e && e.parameter ? e.parameter.payload : null);
}

function doPost(e) {
  return handle(e && e.postData ? e.postData.contents : null);
}

function handle(rawRequest) {
  if (!rawRequest) {
    return json({ error: 'Chybí data požadavku.' });
  }

  // Zámek brání tomu, aby dvě rezervace odeslané naráz
  // přepsaly jedna druhou.
  const lock = LockService.getScriptLock();

  try {
    lock.waitLock(20000);
  } catch (err) {
    return json({ error: 'Tabulka je zaneprázdněná, zkus to znovu.' });
  }

  try {
    const request = JSON.parse(rawRequest);

    if (request.token !== TOKEN) {
      return json({ error: 'Neplatný token.' });
    }

    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
    ensureHeader(sheet);

    switch (request.action) {
      case 'list':
        return json({ rows: listRows(sheet) });

      case 'add':
        return json(addRow(sheet, request.row));

      case 'set_status':
        return json(setStatus(sheet, request.id, request.status));

      case 'delete':
        return json(deleteRow(sheet, request.id));

      case 'ping':
        return json({ ok: true, rows: listRows(sheet).length });

      default:
        return json({ error: 'Neznámá akce: ' + request.action });
    }
  } catch (err) {
    return json({ error: String(err) });
  } finally {
    lock.releaseLock();
  }
}

function json(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

function ensureHeader(sheet) {
  if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, HEADER.length).setValues([HEADER]).setFontWeight('bold');
    sheet.setFrozenRows(1);
  }
}

function listRows(sheet) {
  if (sheet.getLastRow() < 2) {
    return [];
  }

  // Bereme hodnoty tak, jak jsou zobrazené, ať se datum nevrací
  // jako pořadové číslo dne.
  const values = sheet
    .getRange(2, 1, sheet.getLastRow() - 1, HEADER.length)
    .getDisplayValues();

  return values
    .filter(function (row) {
      return String(row[COL_ID - 1]).trim() !== '';
    })
    .map(function (row) {
      const item = {};
      HEADER.forEach(function (name, index) {
        item[name] = row[index];
      });
      return item;
    });
}

function addRow(sheet, row) {
  const id = Utilities.getUuid().replace(/-/g, '').slice(0, 12);

  sheet.appendRow([
    row['Jméno'],
    row['Příjmení'],
    row['email'],
    row['Datum - Start'],
    row['Datum - Konec'],
    row['Stav'],
    id,
    row['Vytvořeno'],
  ]);

  return { ok: true, id: id };
}

function findRow(sheet, id) {
  if (sheet.getLastRow() < 2) {
    return -1;
  }

  const ids = sheet.getRange(2, COL_ID, sheet.getLastRow() - 1, 1).getDisplayValues();

  for (var i = 0; i < ids.length; i++) {
    if (String(ids[i][0]).trim() === String(id).trim()) {
      return i + 2;
    }
  }

  return -1;
}

function setStatus(sheet, id, status) {
  const row = findRow(sheet, id);

  if (row === -1) {
    return { error: 'Rezervace nenalezena: ' + id };
  }

  sheet.getRange(row, COL_STATUS).setValue(status);

  return { ok: true };
}

function deleteRow(sheet, id) {
  const row = findRow(sheet, id);

  if (row === -1) {
    return { error: 'Rezervace nenalezena: ' + id };
  }

  sheet.deleteRow(row);

  return { ok: true };
}
