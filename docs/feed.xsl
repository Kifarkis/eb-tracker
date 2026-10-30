<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="1.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:atom="http://www.w3.org/2005/Atom">
<xsl:output method="html" encoding="utf-8" doctype-system="about:legacy-compat"/>

<xsl:variable name="lang" select="/atom:feed/@xml:lang"/>
<xsl:variable name="title" select="/atom:feed/atom:title"/>
<xsl:variable name="self" select="/atom:feed/atom:link[@rel='self']/@href"/>
<xsl:variable name="site" select="/atom:feed/atom:link[@rel='alternate']/@href"/>

<xsl:template name="t">
  <xsl:param name="sv"/><xsl:param name="da"/><xsl:param name="nb"/><xsl:param name="en"/>
  <xsl:choose>
    <xsl:when test="$lang = 'sv'"><xsl:value-of select="$sv"/></xsl:when>
    <xsl:when test="$lang = 'da'"><xsl:value-of select="$da"/></xsl:when>
    <xsl:when test="$lang = 'nb'"><xsl:value-of select="$nb"/></xsl:when>
    <xsl:otherwise><xsl:value-of select="$en"/></xsl:otherwise>
  </xsl:choose>
</xsl:template>

<xsl:template match="/">
<html lang="{$lang}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="color-scheme" content="light dark"/>
<meta name="robots" content="noindex"/>
<title><xsl:value-of select="$title"/></title>
<link rel="icon" href="icon-192.png" type="image/png"/>
<style>
:root {
  --bg: #faf9f7; --surface: #ffffff;
  --border: rgba(0, 0, 0, 0.08); --border-strong: rgba(0, 0, 0, 0.16);
  --text: #1a1a1a; --text-muted: #595959; --text-faint: #707070;
  --accent: #1858c7;
}
html[data-theme="dark"] {
  --bg: #0f0f10; --surface: #1a1a1c;
  --border: rgba(255, 255, 255, 0.08); --border-strong: rgba(255, 255, 255, 0.18);
  --text: #ededed; --text-muted: #b3b3b3; --text-faint: #8a8a8a;
  --accent: #6ea8ff;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f0f10; --surface: #1a1a1c;
    --border: rgba(255, 255, 255, 0.08); --border-strong: rgba(255, 255, 255, 0.18);
    --text: #ededed; --text-muted: #b3b3b3; --text-faint: #8a8a8a;
    --accent: #6ea8ff;
  }
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: var(--bg); color: var(--text);
  margin: 0; padding: 32px 24px 64px;
  font-size: 15px; line-height: 1.65;
}
.wrap { max-width: 640px; margin: 0 auto; }
.site { font-size: 14px; color: var(--text-muted); text-decoration: none; }
.site:hover { color: var(--accent); }
h1 { font-size: 28px; font-weight: 500; letter-spacing: -0.02em; margin: 8px 0 16px 0; }
p { margin: 0 0 16px 0; color: var(--text-muted); }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.copy { display: flex; gap: 8px; margin: 0 0 32px 0; }
.copy input { flex: 1; min-width: 0; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 13px; padding: 9px 12px; border: 0.5px solid var(--border-strong); border-radius: 8px; background: var(--surface); color: var(--text); }
.copy button { font-family: inherit; font-size: 13px; padding: 9px 16px; border: 0; border-radius: 8px; background: var(--accent); color: #fff; cursor: pointer; white-space: nowrap; }
.copy button:hover { opacity: 0.9; }
ul { list-style: none; margin: 0; padding: 0; }
li { padding: 14px 0; border-top: 0.5px solid var(--border); }
li a { font-weight: 500; }
li p { margin: 2px 0 0 0; font-size: 13px; color: var(--text-faint); font-family: ui-monospace, "SF Mono", Menlo, monospace; }
@media (max-width: 640px) { body { padding: 20px 14px 48px; } }
</style>
<script>
try { var th = localStorage.getItem('sas-theme'); if (th === 'dark' || th === 'light') document.documentElement.setAttribute('data-theme', th); } catch (e) {}
</script>
</head>
<body>
<div class="wrap">
  <a class="site" href="{$site}">EuroBonus Shopping</a>
  <h1><xsl:value-of select="substring-before($title, ' — ')"/> – <xsl:value-of select="substring-after($title, 'EuroBonus Shopping ')"/></h1>
  <p><xsl:call-template name="t">
    <xsl:with-param name="sv">Det här är ett RSS-flöde. Lägg in adressen i en RSS-läsare så får du nya kampanjer automatiskt.</xsl:with-param>
    <xsl:with-param name="da">Dette er et RSS-feed. Indsæt adressen i en RSS-læser, så får du nye kampagner automatisk.</xsl:with-param>
    <xsl:with-param name="nb">Dette er en RSS-feed. Legg inn adressen i en RSS-leser, så får du nye kampanjer automatisk.</xsl:with-param>
    <xsl:with-param name="en">This is an RSS feed. Add the address to a feed reader and new campaigns will come to you automatically.</xsl:with-param>
  </xsl:call-template></p>
  <div class="copy">
    <input id="feed-url" type="text" readonly="readonly" value="{$self}" onfocus="this.select()">
      <xsl:attribute name="aria-label"><xsl:call-template name="t">
        <xsl:with-param name="sv">Flödets adress</xsl:with-param>
        <xsl:with-param name="da">Feedets adresse</xsl:with-param>
        <xsl:with-param name="nb">Feedens adresse</xsl:with-param>
        <xsl:with-param name="en">Feed address</xsl:with-param>
      </xsl:call-template></xsl:attribute>
    </input>
    <button type="button" id="copy-btn">
      <xsl:attribute name="data-done"><xsl:call-template name="t">
        <xsl:with-param name="sv">Kopierad!</xsl:with-param>
        <xsl:with-param name="da">Kopieret!</xsl:with-param>
        <xsl:with-param name="nb">Kopiert!</xsl:with-param>
        <xsl:with-param name="en">Copied!</xsl:with-param>
      </xsl:call-template></xsl:attribute>
      <xsl:call-template name="t">
        <xsl:with-param name="sv">Kopiera adressen</xsl:with-param>
        <xsl:with-param name="da">Kopiér adressen</xsl:with-param>
        <xsl:with-param name="nb">Kopier adressen</xsl:with-param>
        <xsl:with-param name="en">Copy address</xsl:with-param>
      </xsl:call-template>
    </button>
  </div>
  <ul>
    <xsl:for-each select="/atom:feed/atom:entry">
      <li>
        <a href="{atom:link[@rel='alternate']/@href}"><xsl:value-of select="atom:title"/></a>
        <p><xsl:value-of select="atom:summary"/></p>
      </li>
    </xsl:for-each>
  </ul>
</div>
<script>
(function () {
  var input = document.getElementById('feed-url');
  var btn = document.getElementById('copy-btn');
  var label = btn.textContent;
  btn.addEventListener('click', function () {
    function done() { btn.textContent = btn.getAttribute('data-done'); setTimeout(function () { btn.textContent = label; }, 2000); }
    input.focus(); input.select();
    if (navigator.clipboard &amp;&amp; navigator.clipboard.writeText) {
      navigator.clipboard.writeText(input.value).then(done, function () { if (document.execCommand('copy')) done(); });
    } else if (document.execCommand('copy')) done();
  });
})();
</script>
</body>
</html>
</xsl:template>
</xsl:stylesheet>
