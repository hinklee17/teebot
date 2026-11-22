// Email relay for the tee time bot. Runs inside YOUR Google account and sends
// emails from your Gmail when the bot asks. It only ever emails TO (below), so
// even if someone found the URL, all they could do is email you.
//
// Setup: script.google.com -> New project -> paste this -> set SECRET -> Save ->
// Deploy -> New deployment -> Web app -> Execute as: Me, Who has access: Anyone -> Deploy.
// After ANY edit: Deploy -> Manage deployments -> pencil -> Version: New version -> Deploy.

const TO = 'hinklehomesllc@gmail.com';
const SECRET = 'CHANGE-ME-to-a-long-random-phrase';

function out(text) {
  return ContentService.createTextOutput(text);
}

function doPost(e) {
  let d;
  try {
    d = JSON.parse(e.postData.contents);
  } catch (err) {
    return out('bad request');
  }
  if (SECRET.indexOf('CHANGE-ME') === 0) {
    return out('forbidden: SECRET in the script is still the CHANGE-ME placeholder');
  }
  const sent = String((d && d.secret) || '');
  if (sent !== SECRET) {
    return out('forbidden: secret mismatch (bot sent ' + sent.length + ' chars starting "' +
               sent.slice(0, 2) + '", script has ' + SECRET.length + ' chars starting "' +
               SECRET.slice(0, 2) + '")');
  }
  MailApp.sendEmail(TO, String(d.subject || 'Tee time bot').slice(0, 200), String(d.body || ''));
  return out('ok');
}
