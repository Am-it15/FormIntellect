var SERVER_URL = "http://localhost:5000";

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("FormIntellect")
    .addItem("Open", "openSidebar")
    .addSeparator()
    .addItem("Check server status", "checkServer")
    .addToUi();
}

function onHomepageTrigger() { openSidebar(); }

function openSidebar() {
  var html = HtmlService.createHtmlOutputFromFile("Sidebar")
    .setTitle("FormIntellect")
    .setWidth(320);
  SpreadsheetApp.getUi().showSidebar(html);
}

function getSheetNames() {
  return SpreadsheetApp.getActiveSpreadsheet().getSheets().map(function(s) {
    return s.getName();
  });
}

function getSheetColumns(sheetName) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetName);
  if (!sheet) return { error: "Sheet not found: " + sheetName };
  var lastCol = sheet.getLastColumn();
  if (lastCol === 0) return { columns: [], rowCount: 0, submittedCount: 0, pendingCount: 0 };
  var headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  var columns = headers.map(String).filter(function(h) { return h.trim() !== ""; });
  var lastRow = sheet.getLastRow();
  var rowCount = Math.max(0, lastRow - 1);
  var submittedCount = 0;
  var statusIdx = columns.findIndex(function(c) {
    return ["status","submit","submitted"].includes(c.trim().toLowerCase());
  });
  if (statusIdx >= 0 && lastRow > 1) {
    var statusVals = sheet.getRange(2, statusIdx + 1, lastRow - 1, 1).getValues();
    submittedCount = statusVals.filter(function(r) {
      return String(r[0]).toLowerCase() === "submitted";
    }).length;
  }
  return { columns: columns, rowCount: rowCount, submittedCount: submittedCount, pendingCount: rowCount - submittedCount };
}

function pingServer() {
  try {
    var resp = UrlFetchApp.fetch(SERVER_URL + "/api/health", { method: "get", muteHttpExceptions: true, deadline: 5 });
    if (resp.getResponseCode() === 200) {
      var data = JSON.parse(resp.getContentText());
      return { online: true, version: data.version || "1.0.0" };
    }
    return { online: false, error: "HTTP " + resp.getResponseCode() };
  } catch (e) { return { online: false, error: e.message }; }
}

function detectForm(prefilled_link, sheetName) {
  var sheetInfo = getSheetColumns(sheetName);
  if (sheetInfo.error) return { success: false, error: sheetInfo.error };
  var payload = JSON.stringify({ prefilled_link: prefilled_link, columns: sheetInfo.columns, status_col: "Status" });
  try {
    var resp = UrlFetchApp.fetch(SERVER_URL + "/api/detect", {
      method: "post", contentType: "application/json", payload: payload, muteHttpExceptions: true, deadline: 30
    });
    var result = JSON.parse(resp.getContentText());
    result.rowCount       = sheetInfo.rowCount;
    result.submittedCount = sheetInfo.submittedCount;
    result.pendingCount   = sheetInfo.pendingCount;
    return result;
  } catch (e) { return { success: false, error: "Server unreachable: " + e.message }; }
}

function checkServer() {
  var result = pingServer();
  var ui = SpreadsheetApp.getUi();
  if (result.online) {
    ui.alert("FormIntellect server is online (v" + result.version + ")");
  } else {
    ui.alert("Server offline. Run: python -m server.main\n\nError: " + result.error);
  }
}
