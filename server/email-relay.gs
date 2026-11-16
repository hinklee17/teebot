// Email relay for the tee time bot. Runs inside YOUR Google account and sends
// emails from your Gmail when the bot asks. It only ever emails TO (below), so
// even if someone found the URL, all they could do is email you.
//
// Setup: script.google.com -> New project -> paste this -> set SECRET -> Deploy ->
// New deployment -> Web app -> Execute as: Me, Who has access: Anyone -> Deploy.

const TO = 'hinklehomesllc@gmail.com';
const SECRET = 'CHANGE-ME-to-a-long-random-phrase';

function doPost(e) {
  let d;
  try {
    d = JSON.parse(e.postData.contents);
  } catch (err) {
    return ContentService.createTextOutput('bad request');
  }
  if (!d || d.secret !== SECRET || SECRET.indexOf('CHANGE-ME') === 0) {
    return ContentService.createTextOutput('forbidden');
  }
  MailApp.sendEmail(TO, String(d.subject || 'Tee time bot').slice(0, 200), String(d.body || ''));
  return ContentService.createTextOutput('ok');
}
