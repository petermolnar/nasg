<!DOCTYPE html>
<html prefix="og: http://ogp.me/ns# article: http://ogp.me/ns/article#">
<head>
    <!--[if lt IE 9]>
    <script src="https://petermolnar.net/html5shiv-printshiv.js"></script>
    <![endif]-->
    <title>Search results for: <?php echo($_GET['q']); ?></title>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1,minimum-scale=1" />
    <meta name="author" content="Peter Molnar (mail@petermolnar.net)" />
    <link rel="icon" href="https://petermolnar.net/favicon.ico" />
    <!-- <base href="" /> -->
    <link rel="webmention" href="https://webmention.io/petermolnar.net/webmention" />
    <link rel="pingback" href="https://webmention.io/petermolnar.net/xmlrpc" />
    <link rel="hub" href="https://petermolnar.superfeedr.com/" />
    <link rel="authorization_endpoint" href="https://indieauth.com/auth" />
    <link rel="token_endpoint" href="https://tokens.indieauth.com/token" />
    <link rel="micropub" href="https://petermolnar.net/micropub.php" />
    <style media="all">
* {
  -webkit-box-sizing: border-box;
  -moz-box-sizing: border-box;
  box-sizing: border-box;
  font-family: "Courier", monospace;
  margin: 0;
  padding: 0;
  line-height: 1.5em;
}

body {
  color: #eee;
  background-color: #222;
}

body > header,
body > footer {
  background-color: #111;
  text-align: center;
  padding: 0.6em 0;
}

body > main,
body > nav,
body > header > section,
body > footer > section {
  max-width: 88ch;
  margin: 0 auto;
  padding: 0 1em;
}

hr {
  border: none;
}

dt {
  font-weight: bold;
}

h1, h2, h3, h4, h5, h6, hr,
dt {
  margin: 2em 0 0.6em 0;
}

main p {
  margin: 1em 0;
}

h1 {
  border-bottom: 4px double #999;
  text-transform:uppercase;
  text-align: center;
  padding-bottom: 1em;
}

article > footer > dl > dt,
h2 {
  border-bottom: 1px solid #999;
}

article > footer > dl > dt,
h3,
hr {
  border-bottom: 1px dotted #999;
}

h4 {
  border-bottom: 1px dashed #999;
}

svg {
  transform: rotate(0deg);
  fill: currentColor;
  vertical-align:middle;
}

body > svg {
  display: none;
}

a {
  color: #f90;
  text-decoration: none;
  border-bottom: 1px solid transparent;
}

a:hover {
  color: #eee;
  border-bottom: 1px solid #eee;
}

sup {
  vertical-align: unset;
}

sup:before {
  content: '[';
}

sup:after {
  content: ']';
}

input, button, label {
  -webkit-appearance:none;
}

nav > ul {
  list-style-type: none;
}

nav > ul > li {
 display: inline-block;
}

body > header form {
  display: inline-block;
  padding-left: 0.6em;
  margin-top: 1em;
}

body > header a {
  font-weight: bold;
  border-bottom: 3px solid transparent;
  padding-bottom: 0.1em;
}

body > header a:hover,
body > header a.active {
  border-bottom: 3px solid  #eee;
  color: #eee;
}

body > header a svg {
  display: block;
  margin: 0.1em auto;
}

blockquote {
  border-left: 3px solid #999;
  margin: 2em 0 2em 1em;
  padding: 0 0 0 1em;
  color: #aaa;
}

input {
  width: 8em;
  padding: 0 0.3em;
  border: none;
  background-color: #333;
  color: #ccc;
}

.hidden, .theme,
.theme input, input[type=submit] {
  display: none;
}

.theme input + label {
  color: #f90;
  cursor: pointer;
  border-bottom: 3px solid transparent;
  padding-bottom: 0.1em;
}

.theme input:hover + label,
.theme input:checked + label {
  border-bottom: 3px solid #eee;
  color: #eee;
}

body > footer {
  margin-top: 2em;
}

body > footer > section > * {
  margin-bottom: 0.6em;
}

body > footer .email span {
  display: none;
}

video,
figure img {
  display: block;
  max-height: 98vh;
  max-width: 100%;
  width:auto;
  height:auto;
  margin: 0 auto;
  border: 1px solid #000;
}

figure {
  margin: 2em 0;
}

figcaption {
  margin-top: 1em;
}

figcaption > dl {
  margin-top: 1em;
  color: #666;
}

figcaption > dl * {
  display: inline-block;
}

figcaption > dl dt {
  display: none;
}

figcaption > dl dd {
  margin: 0 0.3em;
}

.vcard img {
  height: 1em;
}

code, pre {
  color: #3c3;
  border: 1px solid #666;
  direction: ltr;
  word-break: break-all;
  word-wrap: break-word;
  white-space: pre-wrap;
  overflow:initial;
}

pre {
  padding: 0.6em;
  position: relative;
  margin: 1em 0;
}

code {
  padding: 0.05em 0.2em;
}

pre > code {
  border: none;
}

pre > code::before {
  content: attr(lang);
  float: right;
  color: #999;
  border-left: 1px solid #666;
  border-bottom: 1px solid #666;
  padding: 0 0.3em;
  margin: -0.6em -0.6em 0 0;
}

table {
  border-collapse: collapse;
  width: 100%;
}

td, th {
  padding: 0.3em;
  border: 1px solid #777;
  text-align:left;
}

th {
  font-weight: bold;
}

th, tr:nth-child(even) {
  background-color: rgba(255, 255, 255, .1);
}

main > header > p {
  text-align: center;
}

article > header {
  border-bottom: 4px double #999;
  margin-bottom: 2em;
}

.h-feed article > header {
  border: none;
  margin: 0;
}

main ul {
  margin-left: 2em;
}

main ol {
  margin-left: 3em;
}

li p {
 margin: 0;
}

.footnotes hr:before {
  content: 'Links';
  color: #ccc;
  font-weight: bold;
}

.comments .u-url,
.footnotes a {
  display: inline-block;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  vertical-align: top;
  max-width: 96%;
}

.footnote-back {
  margin: 0 0 0 0.6em;
}

main > section > article {
  padding-left: 1em;
}

body > nav {
  text-align: center;
  margin-top: 2em;
}

body > nav > ul > li {
  margin: 0 0.6em;
}

@media all and (min-width: 58em) {
  body > header > section {
    text-align: left;
    display: flex;
    justify-content:space-between;
  }

  body > header a svg {
    display: inline-block;
  }

  body > header form {
    margin-top: 0;
  }
}

body > img {
  position: fixed;
  bottom: 0;
  right: 0;
  width: 10em;
  height: auto;
}                </style>
    <style id="css_alt" media="speech">
body {
  color: #000;
  background-color: #eee;
}

a {
  color: #3173b4;
}

a:hover {
  color: #014384;
  border-bottom: 1px solid #014384;
}

code,
pre {
  color: #006400;
}

button svg {
  transform: rotate(180deg);
  transition: all 0.2s;
}

blockquote {
  color: #555;
}

td, th {
  border: 1px solid #111;
}

th, tr:nth-child(even) {
  background-color: rgba(0, 0, 0, .1);
}

pre > code::before {
  color: #444;
}    

.footnotes hr::before {
  color: #222;
}

body > header,
body > footer{
  background-color: #333;
  color: #ccc;
}

body > header a,
body > footer a,
.theme input + label {
  color: #71B3F4;
}

input {
  background-color: #222;
}

body > footer a:hover {
  color: #fff;
  border-bottom: 1px solid #fff;
}                    </style>
    <style media="print">

* {
  background-color: #fff !important;
  color: #222;
}

html, body {
  font-size: 10pt !important;
  font-family: Helvetica, sans-serif !important;
}

@page {
  margin: 0.6in 0.5in;
}

.limit,
body > section {
  max-width: 100% !important;
  margin: 0 !important;
}

h1, h2, h3, h4, h5, h6 {
  page-break-after: avoid;
}

h3,
a,
.footnotes a,
.h-feed .h-entry,
code,
pre {
  border: none;
}

p, li, blockquote, figure, .footnotes {
  page-break-inside: avoid !important;
}

a {
  color: #000;
}

td, th {
  border: 1pt solid #666;
}

.footnotes a {
  display: block;
  overflow: visible;
  white-space: normal;
  overflow:visible !important;
  text-overflow:initial !important;
}

.footnote-back {
  display: none;
}

body > header,
body > footer,
video,
audio,
.footnote-backref,
.footnote-back,
.encourage,
.noprint {
  display:none !important;
}

code, pre {
   max-width: 96%;
   page-break-inside: auto;
   font-family: "Courier", "Courier New", monospace !important;
}

pre {
  border: 1pt dotted #666;
  padding: 0.6em;
}

.adaptimg {
  max-height: 35vh;
  max-width: 90vw;
  outline: none;
  border: 1px solid #000;
}

.h-feed .h-entry {
  page-break-after: always;
}    </style>
</head>

<body>


<header>
    <section>
        <nav>
            <ul>
                <li>
                    <a title="home" href="./index.html"  >
                        <svg width="16" height="16">
                            <use xlink:href="#icon-home" />
                        </svg>
                        home
                    </a>
                </li>
                <li>
                    <a title="photos" href="category/photo/index.html"  >
                        <svg width="16" height="16">
                            <use xlink:href="#icon-photo" />
                        </svg>
                        photos
                    </a>
                </li>
                <li>
                    <a title="journal" href="category/journal/index.html"  >
                        <svg width="16" height="16">
                            <use xlink:href="#icon-journal" />
                        </svg>
                        journal
                    </a>
                </li>
                <li>
                    <a title="IT" href="category/article/index.html"  >
                        <svg width="16" height="16">
                            <use xlink:href="#icon-article" />
                        </svg>
                        IT
                    </a>
                </li>
                <li>
                    <a title="notes" href="category/note/index.html"  >
                        <svg width="16" height="16">
                            <use xlink:href="#icon-note" />
                        </svg>
                        notes
                    </a>
                </li>
            </ul>
        </nav>

        <div>
            <form class="theme" aria-hidden="true">
                <svg width="16" height="16">
                    <use xlink:href="#icon-contrast"></use>
                </svg>
                <span>
                    <input name="colorscheme" value="dark" id="darkscheme" type="radio">
                    <label for="darkscheme">dark</label>
                </span>
                <span>
                    <input name="colorscheme" value="light" id="lightscheme" type="radio">
                    <label for="lightscheme">light</label>
                </span>
            </form>
            <form role="search" method="get" action="search.php">
                <label for="qsub">
                    <input type="submit" value="search" id="qsub" name="qsub" />
                    <svg width="16" height="16">
                        <use xlink:href="#icon-search"></use>
                    </svg>
                </label>
                <input type="search" placeholder="search..." value="" name="q" id="q" title="Search for:" />
            </form>
        </div>
    </section>
</header>

<?php
function relurl($from, $to) {
    $from = explode('/', $from);
    $to = explode('/', $to);
    $relpath = '';

    $i = 0;
    while (isset($from[$i]) && isset($to[$i])) {
        if ($from[$i] != $to[$i]) break;
        $i++;
    }
    $j = count( $from ) - 1;
    while ( $i <= $j ) {
        if ( !empty($from[$j]) ) $relpath .= '../';
        $j--;
    }
    while ( isset($to[$i]) ) {
        if ( !empty($to[$i]) ) $relpath .= $to[$i].'/';
        $i++;
    }
    return substr($relpath, 0, -1);
}
?>
<?php const baseurl = 'https://petermolnar.net'; ?>
<main>
    <header>
        <h1>Search results for: <?php echo($_GET['q']); ?></h1>
    </header>
<?php
$db = new SQLite3('./search.sqlite', SQLITE3_OPEN_READONLY);
$q = str_replace('-', '+', $_GET['q']);
$sql = $db->prepare("
    SELECT
        url, category, title, snippet(data, '', '', '[...]', 5, 24)
    FROM
        data
    WHERE
        data MATCH :q
    ORDER BY
        category
");
$sql->bindValue(':q', $q);
$results = $sql->execute();

printf("<dl>");
while ($row = $results->fetchArray(SQLITE3_ASSOC)) {
    printf('<dt><a href="%s">%s</a></dt><dd>%s</dd>', relurl(baseurl, $row['url']), $row['title'], $row["snippet(data, '', '', '[...]', 5, 24)"]);

}
printf("</dl>");
?>
</main>


<footer class="p-author h-card vcard">
    <section>
        <p>
            <a href="https://creativecommons.org/">CC</a>,
            1999-2019,
            <img class="u-photo photo" src="favicon.jpg" alt="Photo of Peter Molnar" />
            <a class="p-name u-url fn url" href="https://petermolnar.net/" rel="me"> Peter Molnar</a>
            <a class="u-email email" rel="me" href="mailto:mail@petermolnar.net">
                <svg width="16" height="16">
                    <use xlink:href="#icon-mail"></use>
                </svg>
                mail@petermolnar.net
            </a>
        </p>
        <nav>
            <ul>
                <li>
                    <a href="https://petermolnar.net/follow/">
                        <svg width="16" height="16"><use xlink:href="#icon-FollowAction" /></svg>
                        follow
                    </a>
                </li>
                <li>
                    <a href="https://petermolnar.net/following.opml">
                        <svg width="16" height="16"><use xlink:href="#icon-following" /></svg>
                        followings
                    </a>
                </li>
                <li>
                    <a rel="me" href="https://github.com/petermolnar">
                        <svg width="16" height="16"><use xlink:href="#icon-github" /></svg>
                        github
                    </a>
                </li>
                <li>
                    <a href="https://petermolnar.net/cv.html" class="u-url">
                        <svg width="16" height="16"><use xlink:href="#icon-resume" /></svg>
                        resume
                    </a>
                </li>
                <li>
                </li>
                <li>
                </li>
                <li>
                </li>
            </ul>
        </nav>
        <nav>
            <a href="https://xn--sr8hvo.ws/%F0%9F%87%BB%F0%9F%87%AE%F0%9F%93%A2/previous">←</a>
                Member of <a href="https://xn--sr8hvo.ws">IndieWeb Webring</a>
            <a href="https://xn--sr8hvo.ws/%F0%9F%87%BB%F0%9F%87%AE%F0%9F%93%A2/next">→</a>
        </nav>
    </section>
    <section>
        <nav>
            <ul>
                <li>
                    <a href="https://indieweb.org/">
                        <svg width="80" height="15">
                            <use xlink:href="#button-indieweb"/>
                        </svg>
                    </a>
                </li>
                <li>
                    <a href="http://microformats.org/">
                        <svg width="80" height="15">
                            <use xlink:href="#button-microformats"/>
                        </svg>
                    </a>
                </li>
                <li>
                    <a href="https://www.w3.org/TR/webmention/">
                        <svg width="80" height="15">
                            <use xlink:href="#button-webmention"/>
                        </svg>
                    </a>
                </li>
                <li>
                    <a href="https://spdx.org/licenses/CC-BY-NC-ND-4.0.html">
                        <svg width="80" height="15">
                            <use xlink:href="#button-cc"/>
                        </svg>
                    </a>
                </li>
                <li>
                    <svg width="80" height="15">
                        <use xlink:href="#button-nojs"/>
                    </svg>
                </li>
            </ul>
        </nav>
    </section>
</footer>

<script>
var DEFAULT_THEME = 'dark';
var ALT_THEME = 'light';
var STORAGE_KEY = 'theme';
var colorscheme = document.getElementsByName('colorscheme');

function indicateTheme(mode) {
    for(var i = colorscheme.length; i--; ) {
        if(colorscheme[i].value == mode) {
            colorscheme[i].checked = true;
        }
    }
}

function applyTheme(mode) {
    var st = document.getElementById('css_alt');
    if (mode == ALT_THEME) {
        st.setAttribute('media', 'all');
    }
    else {
        st.setAttribute('media', 'speech');
    }
}

function setTheme(e) {
    var mode = e.target.value;
    var mql = window.matchMedia('(prefers-color-scheme: ' + ALT_THEME + ')');
    /* user wants == mql match => remove storage */
    if ((mode == DEFAULT_THEME && !mql.matches) || (mode == ALT_THEME && mql.matches)) {
        localStorage.removeItem(STORAGE_KEY);
    }
    else {
        if(confirm("I\'ll need to store your choice in your browser, in a place called localStorage.\n\nAre you OK with this?")) {
            localStorage.setItem(STORAGE_KEY, mode);
        }
    }
    autoTheme(mql);
}

function autoTheme(e) {
    var mode = DEFAULT_THEME;
    try {
        var current = localStorage.getItem(STORAGE_KEY);
    } catch(e) {
        var current = DEFAULT_THEME;
    }
    if ( current != null) {
        mode = current;
    }
    else if (e.matches) {
        mode = ALT_THEME;
    }
    applyTheme(mode);
    indicateTheme(mode);
}

var mql = window.matchMedia('(prefers-color-scheme: ' + ALT_THEME + ')');
autoTheme(mql);
mql.addListener(autoTheme);

var test = 'ping';
try {
    localStorage.setItem(test, test);
    localStorage.removeItem(test);
    for(var i = colorscheme.length; i--; ) {
        colorscheme[i].onclick = setTheme;
    }
    var themeforms = document.getElementsByClassName(STORAGE_KEY);
    for(var i = themeforms.length; i--; ) {
        themeforms[i].style.display = 'inline-block';
    }
} catch(e) {
    console.log('localStorage is not available, manual theme switching is disabled');
}function kcl(cb) {
  var input = '';
  var key = '38384040373937396665';
  document.addEventListener('keydown', function (e) {
    input += ("" + e.keyCode);
    if (input === key) {
      return cb();
    }
    if (!key.indexOf(input)) return;
    input = ("" + e.keyCode);
  });
}

kcl(function () {
    var e = document.createElement('img');
    e.src = '/iddqd.gif';
    document.body.appendChild(e);
})</script>

<svg aria-hidden="true" version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
    <symbol id="icon-github" viewBox="0 0 16 16">
        <path d="M8 0.198c-4.42 0-8 3.582-8 8 0 3.535 2.292 6.533 5.47 7.59 0.4 0.075 0.547-0.172 0.547-0.385 0-0.19-0.007-0.693-0.010-1.36-2.225 0.483-2.695-1.073-2.695-1.073-0.364-0.923-0.89-1.17-0.89-1.17-0.725-0.496 0.056-0.486 0.056-0.486 0.803 0.056 1.225 0.824 1.225 0.824 0.713 1.223 1.873 0.87 2.33 0.665 0.072-0.517 0.278-0.87 0.507-1.070-1.777-0.2-3.644-0.888-3.644-3.953 0-0.873 0.31-1.587 0.823-2.147-0.090-0.202-0.36-1.015 0.070-2.117 0 0 0.67-0.215 2.2 0.82 0.64-0.178 1.32-0.266 2-0.27 0.68 0.004 1.36 0.092 2 0.27 1.52-1.035 2.19-0.82 2.19-0.82 0.43 1.102 0.16 1.915 0.080 2.117 0.51 0.56 0.82 1.273 0.82 2.147 0 3.073-1.87 3.75-3.65 3.947 0.28 0.24 0.54 0.731 0.54 1.48 0 1.071-0.010 1.931-0.010 2.191 0 0.21 0.14 0.46 0.55 0.38 3.201-1.049 5.491-4.049 5.491-7.579 0-4.418-3.582-8-8-8z"></path>
    </symbol>
    <symbol id="icon-paypal" viewBox="0 0 16 16">
        <path d="M4.605 16h-2.069c-0.443 0-0.724-0.353-0.624-0.787l0.099-0.449h1.381c0.444 0 0.891-0.355 0.988-0.788l0.709-3.061c0.1-0.432 0.544-0.787 0.987-0.787h0.589c2.526 0 4.489-0.519 5.893-1.56s2.107-2.4 2.107-4.090c0-0.75-0.13-1.37-0.392-1.859 0-0.011-0.011-0.021-0.011-0.031l0.090 0.050c0.5 0.31 0.88 0.709 1.141 1.209 0.269 0.5 0.399 1.12 0.399 1.861 0 1.69-0.699 3.049-2.109 4.090-1.4 1.030-3.37 1.549-5.889 1.549h-0.6c-0.44 0-0.889 0.35-0.989 0.791l-0.71 3.070c-0.099 0.43-0.54 0.78-0.98 0.78l-0.008 0.012zM2.821 14.203h-2.070c-0.442 0-0.723-0.353-0.624-0.787l2.915-12.629c0.101-0.435 0.543-0.788 0.987-0.788h4.31c0.93 0 1.739 0.065 2.432 0.193 0.69 0.126 1.28 0.346 1.789 0.66 0.491 0.31 0.881 0.715 1.131 1.212 0.259 0.499 0.389 1.12 0.389 1.865 0 1.69-0.701 3.049-2.109 4.079-1.4 1.041-3.371 1.551-5.891 1.551h-0.589c-0.44 0-0.885 0.349-0.985 0.779l-0.707 3.059c-0.099 0.431-0.545 0.781-0.99 0.781l0.011 0.024zM7.785 2.624h-0.676c-0.444 0-0.888 0.353-0.987 0.785l-0.62 2.68c-0.1 0.432 0.18 0.786 0.62 0.786h0.511c1.109 0 1.98-0.229 2.6-0.681 0.619-0.457 0.93-1.103 0.93-1.941 0-0.553-0.201-0.963-0.6-1.227-0.4-0.269-1-0.403-1.791-0.403l0.013 0.001z"></path>
    </symbol>
    <symbol id="icon-monzo" viewBox="0 0 16 16">
        <path d="M14.5 2h-13c-0.825 0-1.5 0.675-1.5 1.5v9c0 0.825 0.675 1.5 1.5 1.5h13c0.825 0 1.5-0.675 1.5-1.5v-9c0-0.825-0.675-1.5-1.5-1.5zM1.5 3h13c0.271 0 0.5 0.229 0.5 0.5v1.5h-14v-1.5c0-0.271 0.229-0.5 0.5-0.5zM14.5 13h-13c-0.271 0-0.5-0.229-0.5-0.5v-4.5h14v4.5c0 0.271-0.229 0.5-0.5 0.5zM2 10h1v2h-1zM4 10h1v2h-1zM6 10h1v2h-1z"></path>
    </symbol>
    <symbol id="icon-lens" viewBox="0 0 16 16">
        <path d="M8 4c-2.209 0-4 1.791-4 4s1.791 4 4 4 4-1.791 4-4-1.791-4-4-4zM8 11c-1.657 0-3-1.344-3-3s1.343-3 3-3 3 1.343 3 3-1.344 3-3 3zM8 0c-4.418 0-8 3.582-8 8s3.582 8 8 8 8-3.582 8-8-3.582-8-8-8zM8 14c-3.313 0-6-2.687-6-6s2.687-6 6-6 6 2.687 6 6-2.687 6-6 6zM8 6.5c-0.829 0-1.5 0.671-1.5 1.5s0.671 1.5 1.5 1.5 1.5-0.671 1.5-1.5-0.671-1.5-1.5-1.5z"></path>
    </symbol>
    <symbol id="icon-focallength" viewBox="0 0 16 16">
        <path d="M6 9h-3v2l-3-3 3-3v2h3zM10 7h3v-2l3 3-3 3v-2h-3z"></path>
    </symbol>
    <symbol id="icon-aperture" viewBox="0 0 16 16">
        <path d="M10.586 6.99l2.845-4.832c-1.428-1.329-3.326-2.158-5.431-2.158-0.499 0-0.982 0.059-1.456 0.146l4.042 6.843zM9.976 10h5.74c0.166-0.643 0.284-1.305 0.284-2 0-1.937-0.715-3.688-1.861-5.072l-4.162 7.072zM8.25 5l-2.704-4.576c-2.25 0.73-4.069 2.399-4.952 4.576h7.656zM7.816 11l2.696 4.559c2.224-0.742 4.020-2.4 4.895-4.559h-7.59zM6.053 6h-5.769c-0.167 0.643-0.283 1.304-0.283 2 0 1.945 0.722 3.705 1.878 5.094l4.175-7.094zM5.459 8.98l-2.872 4.879c1.426 1.316 3.317 2.14 5.413 2.14 0.521 0 1.027-0.059 1.52-0.152l-4.061-6.867z"></path>
    </symbol>
    <symbol id="icon-mail" viewBox="0 0 16 16">
        <path d="M16 6.339v7.089c0 0.786-0.643 1.429-1.429 1.429h-13.143c-0.786 0-1.429-0.643-1.429-1.429v-7.089c0.268 0.295 0.571 0.554 0.902 0.777 1.482 1.009 2.982 2.018 4.438 3.080 0.75 0.554 1.679 1.232 2.652 1.232h0.018c0.973 0 1.902-0.679 2.652-1.232 1.455-1.054 2.955-2.071 4.446-3.080 0.321-0.223 0.625-0.482 0.893-0.777zM16 3.714c0 1-0.741 1.902-1.527 2.446-1.393 0.964-2.795 1.929-4.179 2.902-0.58 0.402-1.563 1.223-2.286 1.223h-0.018c-0.723 0-1.705-0.821-2.286-1.223-1.384-0.973-2.786-1.938-4.17-2.902-0.634-0.429-1.536-1.438-1.536-2.25 0-0.875 0.473-1.625 1.429-1.625h13.143c0.777 0 1.429 0.643 1.429 1.429z"></path>
    </symbol>
    <symbol id="icon-reply" viewBox="0 0 16 16">
        <path d="M7 12.119v3.881l-6-6 6-6v3.966c6.98 0.164 6.681-4.747 4.904-7.966 4.386 4.741 3.455 12.337-4.904 12.119z"></path>
    </symbol>
    <symbol id="icon-link" viewBox="0 0 16 16">
        <path d="M6.879 9.934c-0.208 0-0.416-0.079-0.575-0.238-1.486-1.486-1.486-3.905 0-5.392l3-3c0.72-0.72 1.678-1.117 2.696-1.117s1.976 0.397 2.696 1.117c1.486 1.487 1.486 3.905 0 5.392l-1.371 1.371c-0.317 0.317-0.832 0.317-1.149 0s-0.317-0.832 0-1.149l1.371-1.371c0.853-0.853 0.853-2.241 0-3.094-0.413-0.413-0.963-0.641-1.547-0.641s-1.134 0.228-1.547 0.641l-3 3c-0.853 0.853-0.853 2.241 0 3.094 0.317 0.317 0.317 0.832 0 1.149-0.159 0.159-0.367 0.238-0.575 0.238z"></path>
        <path d="M4 15.813c-1.018 0-1.976-0.397-2.696-1.117-1.486-1.486-1.486-3.905 0-5.392l1.371-1.371c0.317-0.317 0.832-0.317 1.149 0s0.317 0.832 0 1.149l-1.371 1.371c-0.853 0.853-0.853 2.241 0 3.094 0.413 0.413 0.962 0.641 1.547 0.641s1.134-0.228 1.547-0.641l3-3c0.853-0.853 0.853-2.241 0-3.094-0.317-0.317-0.317-0.832 0-1.149s0.832-0.317 1.149 0c1.486 1.486 1.486 3.905 0 5.392l-3 3c-0.72 0.72-1.678 1.117-2.696 1.117z"></path>
    </symbol>
    <symbol id="icon-FollowAction" viewBox="0 0 16 16">
        <path d="M14.5 0h-13c-0.825 0-1.5 0.675-1.5 1.5v13c0 0.825 0.675 1.5 1.5 1.5h13c0.825 0 1.5-0.675 1.5-1.5v-13c0-0.825-0.675-1.5-1.5-1.5zM4.359 12.988c-0.75 0-1.359-0.603-1.359-1.353 0-0.744 0.609-1.356 1.359-1.356 0.753 0 1.359 0.613 1.359 1.356 0 0.75-0.609 1.353-1.359 1.353zM7.772 13c0-1.278-0.497-2.481-1.397-3.381-0.903-0.903-2.1-1.4-3.375-1.4v-1.956c3.713 0 6.738 3.022 6.738 6.737h-1.966zM11.244 13c0-4.547-3.697-8.25-8.241-8.25v-1.956c5.625 0 10.203 4.581 10.203 10.206h-1.963z"></path>
    </symbol>
    <symbol id="icon-home" viewBox="0 0 16 16">
        <path d="M16 9.226l-8-6.21-8 6.21v-2.532l8-6.21 8 6.21zM14 9v6h-4v-4h-4v4h-4v-6l6-4.5z"></path>
    </symbol>
    <symbol id="icon-note" viewBox="0 0 16 16">
        <path d="M14.341 3.579c-0.347-0.473-0.831-1.027-1.362-1.558s-1.085-1.015-1.558-1.362c-0.806-0.591-1.197-0.659-1.421-0.659h-7.75c-0.689 0-1.25 0.561-1.25 1.25v13.5c0 0.689 0.561 1.25 1.25 1.25h11.5c0.689 0 1.25-0.561 1.25-1.25v-9.75c0-0.224-0.068-0.615-0.659-1.421zM12.271 2.729c0.48 0.48 0.856 0.912 1.134 1.271h-2.406v-2.405c0.359 0.278 0.792 0.654 1.271 1.134zM14 14.75c0 0.136-0.114 0.25-0.25 0.25h-11.5c-0.135 0-0.25-0.114-0.25-0.25v-13.5c0-0.135 0.115-0.25 0.25-0.25 0 0 7.749-0 7.75 0v3.5c0 0.276 0.224 0.5 0.5 0.5h3.5v9.75z"></path>
        <path d="M11.5 13h-7c-0.276 0-0.5-0.224-0.5-0.5s0.224-0.5 0.5-0.5h7c0.276 0 0.5 0.224 0.5 0.5s-0.224 0.5-0.5 0.5z"></path>
        <path d="M11.5 11h-7c-0.276 0-0.5-0.224-0.5-0.5s0.224-0.5 0.5-0.5h7c0.276 0 0.5 0.224 0.5 0.5s-0.224 0.5-0.5 0.5z"></path>
        <path d="M11.5 9h-7c-0.276 0-0.5-0.224-0.5-0.5s0.224-0.5 0.5-0.5h7c0.276 0 0.5 0.224 0.5 0.5s-0.224 0.5-0.5 0.5z"></path>
    </symbol>
    <symbol id="icon-article" viewBox="0 0 16 16">
        <path d="M0 1v14h16v-14h-16zM15 14h-14v-12h14v12zM14 3h-12v10h12v-10zM7 8h-1v1h-1v1h-1v-1h1v-1h1v-1h-1v-1h-1v-1h1v1h1v1h1v1zM11 10h-3v-1h3v1z"></path>
    </symbol>
    <symbol id="icon-journal" viewBox="0 0 16 16">
        <path d="M13.5 0h-12c-0.825 0-1.5 0.675-1.5 1.5v13c0 0.825 0.675 1.5 1.5 1.5h12c0.825 0 1.5-0.675 1.5-1.5v-13c0-0.825-0.675-1.5-1.5-1.5zM13 14h-11v-12h11v12zM4 7h7v1h-7zM4 9h7v1h-7zM4 11h7v1h-7zM4 5h7v1h-7z"></path>
    </symbol>
    <symbol id="icon-photo" viewBox="0 0 18 16">
        <path d="M17 2h-1v-1c0-0.55-0.45-1-1-1h-14c-0.55 0-1 0.45-1 1v12c0 0.55 0.45 1 1 1h1v1c0 0.55 0.45 1 1 1h14c0.55 0 1-0.45 1-1v-12c0-0.55-0.45-1-1-1zM2 3v10h-0.998c-0.001-0.001-0.001-0.001-0.002-0.002v-11.996c0.001-0.001 0.001-0.001 0.002-0.002h13.996c0.001 0.001 0.001 0.001 0.002 0.002v0.998h-12c-0.55 0-1 0.45-1 1v0zM17 14.998c-0.001 0.001-0.001 0.001-0.002 0.002h-13.996c-0.001-0.001-0.001-0.001-0.002-0.002v-11.996c0.001-0.001 0.001-0.001 0.002-0.002h13.996c0.001 0.001 0.001 0.001 0.002 0.002v11.996z"></path>
        <path d="M15 5.5c0 0.828-0.672 1.5-1.5 1.5s-1.5-0.672-1.5-1.5 0.672-1.5 1.5-1.5 1.5 0.672 1.5 1.5z"></path>
        <path d="M16 14h-12v-2l3.5-6 4 5h1l3.5-3z"></path>
    </symbol>
    <symbol id="icon-contrast" viewBox="0 0 16 16">
        <path d="M8 0c-4.418 0-8 3.582-8 8s3.582 8 8 8 8-3.582 8-8-3.582-8-8-8zM2 8c0-3.314 2.686-6 6-6v12c-3.314 0-6-2.686-6-6z"></path>
    </symbol>
    <symbol id="icon-sensitivity" viewBox="0 0 16 16">
        <path d="M8 4c-2.209 0-4 1.791-4 4s1.791 4 4 4 4-1.791 4-4-1.791-4-4-4zM8 10.5v-5c1.379 0 2.5 1.122 2.5 2.5s-1.121 2.5-2.5 2.5zM8 13c0.552 0 1 0.448 1 1v1c0 0.552-0.448 1-1 1s-1-0.448-1-1v-1c0-0.552 0.448-1 1-1zM8 3c-0.552 0-1-0.448-1-1v-1c0-0.552 0.448-1 1-1s1 0.448 1 1v1c0 0.552-0.448 1-1 1zM15 7c0.552 0 1 0.448 1 1s-0.448 1-1 1h-1c-0.552 0-1-0.448-1-1s0.448-1 1-1h1zM3 8c0 0.552-0.448 1-1 1h-1c-0.552 0-1-0.448-1-1s0.448-1 1-1h1c0.552 0 1 0.448 1 1zM12.95 11.536l0.707 0.707c0.39 0.39 0.39 1.024 0 1.414s-1.024 0.39-1.414 0l-0.707-0.707c-0.39-0.39-0.39-1.024 0-1.414s1.024-0.39 1.414 0zM3.050 4.464l-0.707-0.707c-0.391-0.391-0.391-1.024 0-1.414s1.024-0.391 1.414 0l0.707 0.707c0.391 0.391 0.391 1.024 0 1.414s-1.024 0.391-1.414 0zM12.95 4.464c-0.39 0.391-1.024 0.391-1.414 0s-0.39-1.024 0-1.414l0.707-0.707c0.39-0.391 1.024-0.391 1.414 0s0.39 1.024 0 1.414l-0.707 0.707zM3.050 11.536c0.39-0.39 1.024-0.39 1.414 0s0.391 1.024 0 1.414l-0.707 0.707c-0.391 0.39-1.024 0.39-1.414 0s-0.391-1.024 0-1.414l0.707-0.707z"></path>
    </symbol>
    <symbol id="icon-clock" viewBox="0 0 16 16">
        <path d="M10.293 11.707l-3.293-3.293v-4.414h2v3.586l2.707 2.707zM8 0c-4.418 0-8 3.582-8 8s3.582 8 8 8 8-3.582 8-8-3.582-8-8-8zM8 14c-3.314 0-6-2.686-6-6s2.686-6 6-6c3.314 0 6 2.686 6 6s-2.686 6-6 6z"></path>
    </symbol>
    <symbol id="icon-camera" viewBox="0 0 16 16">
        <path d="M4.75 9.5c0 1.795 1.455 3.25 3.25 3.25s3.25-1.455 3.25-3.25-1.455-3.25-3.25-3.25-3.25 1.455-3.25 3.25zM15 4h-3.5c-0.25-1-0.5-2-1.5-2h-4c-1 0-1.25 1-1.5 2h-3.5c-0.55 0-1 0.45-1 1v9c0 0.55 0.45 1 1 1h14c0.55 0 1-0.45 1-1v-9c0-0.55-0.45-1-1-1zM8 13.938c-2.451 0-4.438-1.987-4.438-4.438s1.987-4.438 4.438-4.438c2.451 0 4.438 1.987 4.438 4.438s-1.987 4.438-4.438 4.438zM15 7h-2v-1h2v1z"></path>
    </symbol>
    <symbol id="icon-following" viewBox="0 0 16 16">
        <path d="M5.295 8c-0.929 0.027-1.768 0.429-2.366 1.143h-1.196c-0.893 0-1.732-0.429-1.732-1.42 0-0.723-0.027-3.152 1.107-3.152 0.188 0 1.116 0.759 2.321 0.759 0.411 0 0.804-0.071 1.187-0.205-0.027 0.196-0.045 0.393-0.045 0.589 0 0.813 0.259 1.616 0.723 2.286zM14.857 13.688c0 1.446-0.955 2.313-2.384 2.313h-7.804c-1.429 0-2.384-0.866-2.384-2.313 0-2.018 0.473-5.116 3.089-5.116 0.304 0 1.411 1.241 3.196 1.241s2.893-1.241 3.196-1.241c2.616 0 3.089 3.098 3.089 5.116zM5.714 2.286c0 1.259-1.027 2.286-2.286 2.286s-2.286-1.027-2.286-2.286 1.027-2.286 2.286-2.286 2.286 1.027 2.286 2.286zM12 5.714c0 1.893-1.536 3.429-3.429 3.429s-3.429-1.536-3.429-3.429 1.536-3.429 3.429-3.429 3.429 1.536 3.429 3.429zM17.143 7.723c0 0.991-0.839 1.42-1.732 1.42h-1.196c-0.598-0.714-1.438-1.116-2.366-1.143 0.464-0.67 0.723-1.473 0.723-2.286 0-0.196-0.018-0.393-0.045-0.589 0.384 0.134 0.777 0.205 1.188 0.205 1.205 0 2.134-0.759 2.321-0.759 1.134 0 1.107 2.429 1.107 3.152zM16 2.286c0 1.259-1.027 2.286-2.286 2.286s-2.286-1.027-2.286-2.286 1.027-2.286 2.286-2.286 2.286 1.027 2.286 2.286z"></path>
    </symbol>
    <symbol id="icon-search" viewBox="0 0 16 16">
        <path d="M15.504 13.616l-3.79-3.223c-0.392-0.353-0.811-0.514-1.149-0.499 0.895-1.048 1.435-2.407 1.435-3.893 0-3.314-2.686-6-6-6s-6 2.686-6 6 2.686 6 6 6c1.486 0 2.845-0.54 3.893-1.435-0.016 0.338 0.146 0.757 0.499 1.149l3.223 3.79c0.552 0.613 1.453 0.665 2.003 0.115s0.498-1.452-0.115-2.003zM6 10c-2.209 0-4-1.791-4-4s1.791-4 4-4 4 1.791 4 4-1.791 4-4 4z"></path>
    </symbol>
    <symbol id="icon-resume" viewBox="0 0 16 16">
        <path d="M13.5 0h-12c-0.825 0-1.5 0.675-1.5 1.5v13c0 0.825 0.675 1.5 1.5 1.5h12c0.825 0 1.5-0.675 1.5-1.5v-13c0-0.825-0.675-1.5-1.5-1.5zM13 14h-11v-12h11v12zM4 9h7v1h-7zM4 11h7v1h-7zM5 4.5c0-0.828 0.672-1.5 1.5-1.5s1.5 0.672 1.5 1.5c0 0.828-0.672 1.5-1.5 1.5s-1.5-0.672-1.5-1.5zM7.5 6h-2c-0.825 0-1.5 0.45-1.5 1v1h5v-1c0-0.55-0.675-1-1.5-1z"></path>
    </symbol>
    <symbol id="icon-bookmark" viewBox="0 0 16 16">
        <path d="M4 2v14l5-5 5 5v-14zM12 0h-10v14l1-1v-12h9z"></path>
    </symbol>
    <symbol id="icon-star" viewBox="0 0 16 16">
        <path d="M16 6.204l-5.528-0.803-2.472-5.009-2.472 5.009-5.528 0.803 4 3.899-0.944 5.505 4.944-2.599 4.944 2.599-0.944-5.505 4-3.899z"></path>
    </symbol>
    <symbol id="button-indieweb" viewBox="0 0 80 15">
        <rect width="80" height="15" fill="#666"/>
        <rect x="1" y="1" width="78" height="13" fill="#fff"/>
        <path d="m3 4v2h7v-2h-7zm0 3v4h7v-4h-7z" fill="#fc0d1b"/>
        <path d="m11 4v2h1v-2h-1zm1 2v3h1v-3h-1zm1 0h1v3h1v2h2v-2h1v-3h1v-2h-6v2zm1 3h-1v2h1v-2z" fill="#fc5d20"/>
        <polygon points="21 4 25 4 25 5 26 5 26 7 22 7 22 8 26 8 26 10 25 10 25 11 21 11 21 10 20 10 20 8 19 8 19 7 20 7 20 5 21 5" fill="#fdb02a"/>
        <rect x="29" y="2" width="49" height="1" fill="#fda829"/>
        <rect x="29" y="3" width="49" height="1" fill="#fd9c27"/>
        <rect x="29" y="4" width="49" height="1" fill="#fd9025"/>
        <rect x="29" y="5" width="49" height="1" fill="#fd8124"/>
        <rect x="29" y="6" width="49" height="1" fill="#fd7222"/>
        <rect x="29" y="7" width="49" height="1" fill="#fd6420"/>
        <rect x="29" y="8" width="49" height="1" fill="#fc561f"/>
        <rect x="29" y="9" width="49" height="1" fill="#fc481e"/>
        <rect x="29" y="10" width="49" height="1" fill="#fc371d"/>
        <rect x="29" y="11" width="49" height="1" fill="#fc291c"/>
        <rect x="29" y="12" width="49" height="1" fill="#fc1c1c"/>
        <g fill="#fff">
            <path d="m34 5h1v5h-1z"/>
            <path d="m37 5h1v1h1v1h1v1h1v-3h1v5h-1v-1h-1v-1h-1v-1h-1v3h-1z"/>
            <path d="m44 5v5h3v-1h-2v-3h2v-1h-3zm3 1v3h1v-3h-1z"/>
            <path d="m50 5h1v5h-1z"/>
            <path d="m53 5h3v1h-2v1h2v1h-2v1h2v1h-3z"/>
            <path d="m58 5h1v4h1v-3h1v3h1v-4h1v4h-1v1h-1v-1h-1v1h-1v-1h-1z"/>
            <path d="m65 5h3v1h-2v1h2v1h-2v1h2v1h-3z"/>
            <path d="m70 5v5h3v-1h-2v-1h2v-1h-2v-1h2v-1h-3zm3 1v1h1v-1h-1zm0 2v1h1v-1h-1z"/>
        </g>
    </symbol>
    <symbol id="button-webmention" viewBox="0 0 80 15">
        <rect width="80" height="15" fill="#666"/>
        <rect x="1" y="1" width="78" height="13" fill="#fff" style="paint-order:markers fill stroke"/>
        <path d="m13 1v1h-1v1h-1v1h1 1v1h-1v2h-1v2h-1v-3h-1v-2h-1v2h-1v3h-1v-2h-1v-3h-1v-2h-1-1v2h1v3h1v3h1v3h1 1v-3h1v-2h1v2h1v3h1 1v-3h1v-3h1v-3h1 1v-1h-1v-1h-1v-1h-1z" fill="#610371"/>
        <rect x="19" y="2" width="59" height="11" fill="#850e9a"/>
        <g fill="#fff">
            <path d="m33 5v5h3v-1h-2v-1h2v-1h-2v-1h2v-1h-3zm3 1v1h1v-1h-1zm0 2v1h1v-1h-1z"/>
            <path d="m28 5h3v1h-2v1h2v1h-2v1h2v1h-3z"/>
            <path d="m21 5h1v4h1v-3h1v3h1v-4h1v4h-1v1h-1v-1h-1v1h-1v-1h-1z"/>
            <path d="m39 5h1v1h1v1h1v-1h1v-1h1v5h-1v-3h-1v1h-1v-1h-1v3h-1z"/>
            <path d="m51 5h1v1h1v1h1v1h1v-3h1v5h-1v-1h-1v-1h-1v-1h-1v3h-1z"/>
            <path d="m58 5h3v1h-1v4h-1v-4h-1"/>
            <path d="m63 5h1v5h-1z"/>
            <path d="m67 5v1h2v-1zm2 1v3h1v-3zm0 3h-2v1h2zm-2 0v-3h-1v3z"/>
            <path d="m71 5h1v1h1v1h1v1h1v-3h1v5h-1v-1h-1v-1h-1v-1h-1v3h-1z"/>
            <path d="m46 5h3v1h-2v1h2v1h-2v1h2v1h-3z"/>
        </g>
    </symbol>
    <symbol id="button-microformats" viewBox="0 0 80 15">
        <rect width="80" height="15" fill="#666"/>
        <rect x="1" y="1" width="78" height="13" fill="#fff"/>
        <rect x="18" y="2" width="2" height="11" fill="#5d8f17"/>
        <rect x="20" y="2" width="2" height="11" fill="#609218"/>
        <rect x="22" y="2" width="2" height="11" fill="#639519"/>
        <rect x="24" y="2" width="2" height="11" fill="#66981a"/>
        <rect x="26" y="2" width="2" height="11" fill="#699b1b"/>
        <rect x="28" y="2" width="2" height="11" fill="#6c9e1b"/>
        <rect x="30" y="2" width="2" height="11" fill="#6fa11c"/>
        <rect x="32" y="2" width="2" height="11" fill="#72a51d"/>
        <rect x="34" y="2" width="2" height="11" fill="#76a81e"/>
        <rect x="36" y="2" width="2" height="11" fill="#78aa1f"/>
        <rect x="38" y="2" width="2" height="11" fill="#7cae20"/>
        <rect x="40" y="2" width="2" height="11" fill="#7eb120"/>
        <rect x="42" y="2" width="2" height="11" fill="#82b421"/>
        <rect x="44" y="2" width="2" height="11" fill="#85b722"/>
        <rect x="46" y="2" width="2" height="11" fill="#88ba23"/>
        <rect x="48" y="2" width="2" height="11" fill="#8bbd24"/>
        <rect x="50" y="2" width="2" height="11" fill="#8ec125"/>
        <rect x="52" y="2" width="2" height="11" fill="#91c325"/>
        <rect x="54" y="2" width="2" height="11" fill="#94c626"/>
        <rect x="56" y="2" width="2" height="11" fill="#97ca27"/>
        <rect x="58" y="2" width="2" height="11" fill="#9acd28"/>
        <rect x="60" y="2" width="2" height="11" fill="#9dd029"/>
        <rect x="62" y="2" width="2" height="11" fill="#a0d32a"/>
        <rect x="64" y="2" width="2" height="11" fill="#a4d62b"/>
        <rect x="66" y="2" width="2" height="11" fill="#a6d92b"/>
        <rect x="68" y="2" width="2" height="11" fill="#a8db2c"/>
        <rect x="70" y="2" width="2" height="11" fill="#acdf2d"/>
        <rect x="72" y="2" width="2" height="11" fill="#b0e32e"/>
        <rect x="74" y="2" width="2" height="11" fill="#b3e62f"/>
        <rect x="76" y="2" width="2" height="11" fill="#b6e92f"/>
        <polygon points="4 4 6 4 6 9 7 9 7 10 12 10 12 12 11 12 11 13 4 13 4 12 3 12 3 5 4 5" fill="#5c8d17"/>
        <polygon points="7 3 9 3 9 6 10 6 10 7 13 7 13 9 8 9 8 8 7 8" fill="#8dc024"/>
        <polygon points="10 2 13 2 13 3 14 3 14 6 11 6 11 5 10 5" fill="#a5d82b"/>
        <g fill="#fff">
            <path d="m20 5h1v1h1v1h1v-1h1v-1h1v5h-1v-3h-1v1h-1v-1h-1v3h-1z"/>
            <path d="m26 5h1v5h-1z"/>
            <path d="m29 5h2v1h1v1h-1v-1h-2v3h2v-1h1v1h-1v1h-2v-1h-1v-3h1z"/>
            <path d="m33 5v5h1v-2h1v1h1v-2h-2v-1h2v-1h-3zm3 1v1h1v-1h-1zm0 3v1h1v-1h-1z"/>
            <path d="m39 5v1h2v-1h-2zm2 1v1 1 1h1v-1-1-1h-1zm0 3h-2v1h2v-1zm-2 0v-3h-1v3h1z"/>
            <path d="m43 5h3v1h-2v1h2v1h-2v2h-1z"/>
            <path d="m48 5v1h2v-1h-2zm2 1v1 1 1h1v-1-1-1h-1zm0 3h-2v1h2v-1zm-2 0v-3h-1v3h1z"/>
            <path d="m52 5v5h1v-2h1v1h1v-2h-2v-1h2v-1h-3zm3 1v1h1v-1h-1zm0 3v1h1v-1h-1z"/>
            <path d="m57 5h1v1h1v1h1v-1h1v-1h1v5h-1v-3h-1v1h-1v-1h-1v3h-1z"/>
            <path d="m64 5v1h2v-1h-2zm2 1v1h-2v-1h-1v4h1v-2h2v2h1v-4h-1z"/>
            <path d="m68 5h3v1h-1v4h-1v-4h-1"/>
            <path d="m73 5h3v1h-3v1h2v1h1v1h-1v1h-3v-1h3v-1h-2v-1h-1v-1h1"/>
        </g>
    </symbol>
    <symbol id="button-cc" viewBox="0 0 80 15">
        <rect y="0" width="80" height="15" fill="#000"/>
        <rect x="1" y="1" width="78" height="13" fill="#fff"/>
        <rect x="2" y="2" width="76" height="11" fill="#000"/>
        <g fill="#fff">
            <path d="m42 5h1v1h1v1h1v-1h1v-1h1v5h-1v-3h-1v1h-1v-1h-1v3h-1z"/>
            <path d="m31 5h2v1h1v1h-1v-1h-2v3h2v-1h1v1h-1v1h-2v-1h-1v-3h1z"/>
            <path d="m37 5v1h2v-1zm2 1v3h1v-3zm0 3h-2v1h2zm-2 0v-3h-1v3z"/>
            <path d="m57 5v1h2v-1zm2 1v3h1v-3zm0 3h-2v1h2zm-2 0v-3h-1v3z"/>
            <path d="m49 5h1v1h1v1h1v-1h1v-1h1v5h-1v-3h-1v1h-1v-1h-1v3h-1z"/>
            <path d="m70 5h3v1h-3v1h2v1h1v1h-1v1h-3v-1h3v-1h-2v-1h-1v-1h1"/>
            <path d="m62 5h1v1h1v1h1v1h1v-3h1v5h-1v-1h-1v-1h-1v-1h-1v3h-1z"/>
        </g>
        <path d="m2 2v11h19.891a8.5136 8.5 0 0 0 2.1088-5.5898 8.5136 8.5 0 0 0-1.9563-5.4102h-13.119z" fill="#aaa"/>
        <path d="m6.0195 2a8.5 8.5 0 0 0-2.0195 5.5 8.5 8.5 0 0 0 2.0312 5.5h12.949a8.5 8.5 0 0 0 2.0195-5.5 8.5 8.5 0 0 0-2.0312-5.5z" fill="#000"/>
        <circle cx="12.5" cy="7.5" r="6.5" fill="#fff"/>
        <path d="m9 5h2v1h1v1h-1v-1h-2v3h2v-1h1v1h-1v1h-2v-1h-1v-3h1z" fill="#000"/>
        <path d="m14 5h2v1h1v1h-1v-1h-2v3h2v-1h1v1h-1v1h-2v-1h-1v-3h1z" fill="#000"/>
    </symbol>
    <symbol id="button-nojs" viewBox="0 0 80 15">
        <rect width="80" height="15" fill="#666"/>
        <rect x="1" y="1" width="78" height="13" fill="#fff"/>
        <rect x="16" y="2" width="62" height="11" fill="#666"/>
        <g fill="#fff">
            <path d="m27 5v1h2v-1zm2 1v3h1v-3zm0 3h-2v1h2zm-2 0v-3h-1v3z"/>
            <path d="m20 5h1v1h1v1h1v1h1v-3h1v5h-1v-1h-1v-1h-1v-1h-1v3h-1z"/>
            <rect x="-1" y="259.03" width="78" height="13"/>
            <path d="m70 5v5h3v-1h-2v-3h2v-1zm3 1v3h1v-3z"/>
            <path d="m66 5h3v1h-2v1h2v1h-2v1h2v1h-3z"/>
            <circle cx="7.5" cy="7.5" r="5.5" stroke="#666"/>
        </g>
        <g fill="#666">
            <rect transform="rotate(-45)" x="-6" y="10" width="11" height="1"/>
            <path d="m9 5h3v1h-3v1h2v1h1v1h-1v1h-3v-1h3v-1h-2v-1h-1v-1h1"/>
            <path d="m6 5v4h1v-4zm0 4h-2v1h2zm-2 0v-1h-1v1z"/>
        </g>
        <g fill="#fff">
            <path d="m40 5h3v1h-3v1h2v1h1v1h-1v1h-3v-1h3v-1h-2v-1h-1v-1h1"/>
            <path d="m37 5v4h1v-4zm0 4h-2v1h2zm-2 0v-1h-1v1z"/>
            <path d="m57 5h3v1h-2v1h2v1h-2v1h2v1h-3z"/>
            <path d="m61 5v5h3v-1h-2v-3h2v-1zm3 1v3h1v-3z"/>
            <path d="m53 5h3v1h-2v1h2v1h-2v1h2v1h-3z"/>
            <path d="m47 5h1v1h1v1h1v1h1v-3h1v5h-1v-1h-1v-1h-1v-1h-1v3h-1z"/>
        </g>
    </symbol>
</svg>

    </body>
</html>