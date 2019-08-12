<?php

$redirects = array(
{% for from, to in redirects.items() %}
    "{{ from }}" => "{{ to }}",
{% endfor %}
);

$rewrites = array(
{% for from, to in rewrites.items() %}
    "{{ from }}" => "{{ to }}",
{% endfor %}
);

$gone = array(
{% for gone in gones %}
    "{{ gone }}" => true,
{% endfor %}
);

$gone_re = array(
{% for gone in gone_re %}
    "{{ gone }}",
{% endfor %}
);

function redirect_to($uri) {
    header('HTTP/1.1 301 Moved Permanently');
    if (preg_match("/^https?/", $uri))
        $target = $uri;
    else
        $target = '{{ site.url }}/'.  trim($uri, '/') . '/';
    header("Location: ". $target);
    exit;
}

function gone($uri) {
    header('HTTP/1.1 410 Gone');
    die('<!DOCTYPE html>
<html lang="en">
 <head>
  <meta charset="utf-8"/>
  <meta content="width=device-width,initial-scale=1,minimum-scale=1" name="viewport"/>
  <title>Gone</title>
 </head>
 <body>
<h1><center>This content was deleted.</center></h1>
<hr>
<p><center>'.$uri.'</center></p>
 </body>
</html>');
}

function notfound($uri) {
    header('HTTP/1.0 404 Not Found');
    die('<!DOCTYPE html>
<html lang="en">
 <head>
  <meta charset="utf-8"/>
  <meta content="width=device-width,initial-scale=1,minimum-scale=1" name="viewport"/>
  <title>Not found</title>
 </head>
 <body>

<h1><center>This was not found.</center></h1>
<h2><center>Please search for it instead.</center></h2>
<p>
    <center>
        <form action="/search.php" class="search-form" method="get" role="search">
            <label for="search">Search</label>
            <input id="q" name="q" placeholder="search..." title="Search for:" type="search" value=""/>
            <input type="submit" value="OK"/>
        </form>
    </center>
</p>
<hr>
<p><center>'.$uri.'</center></p>
 </body>
</html>');
}

function maybe_redirect($uri) {
    if (file_exists("./$uri/index.html")) {
        redirect_to($uri);
    }
}

$uri = filter_var($_SERVER['REQUEST_URI'], FILTER_SANITIZE_URL);
$uri = str_replace('../', '', $uri);
$uri = str_replace('/feed/', '', $uri);
$uri = str_replace('/atom/', '', $uri);
$uri = trim($uri, '/');

foreach ($gone_re as $pattern) {
    if (preg_match(sprintf('/%s/', $pattern), $uri)) {
        gone($uri);
    }
}

foreach ($rewrites as $pattern => $target) {
    $maybe = preg_match(sprintf('/%s/i', $pattern), $uri, $matches);
    if ($maybe) {
        $target = str_replace('$1', $matches[1], $target);
        redirect_to($target);
    }
}

if (isset($gone[$uri])) {
    gone($uri);
}
elseif (isset($redirects[$uri])) {
    redirect_to($redirects[$uri]);
}
elseif (strstr($uri, '_')) {
    maybe_redirect(str_replace('_', '-', $uri));
}
else {
    notfound($uri);
}
