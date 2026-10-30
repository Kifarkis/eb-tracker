(function () {
  var LATEST = '2026-10-28';
  var KEY = 'sas-news-seen';
  var seen;
  try { seen = localStorage.getItem(KEY) || ''; } catch (e) { return; }
  if (document.getElementById('news-page')) {
    try { localStorage.setItem(KEY, LATEST); } catch (e) {}
    return;
  }
  if (seen >= LATEST) return;
  var links = document.querySelectorAll('.sas-news');
  for (var i = 0; i < links.length; i++) links[i].classList.add('is-unseen');
})();
