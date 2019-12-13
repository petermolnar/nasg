<?php

function _syslog($msg) {
    $trace = debug_backtrace();
    $caller = $trace[1];
    $parent = $caller['function'];
    if (isset($caller['class'])) {
        $parent = $caller['class'] . '::' . $parent;
    }
    return error_log( "{$parent}: {$msg}" );
}

function notimplemented() {
    header('HTTP/1.1 501 Not Implemented');
    die("This functionality is yet to be implemented");
}

function unauthorized($text) {
    header('HTTP/1.1 401 Unauthorized');
    _syslog("unauth:" . $text);
    die($text);
}

function badrequest($text) {
    header('HTTP/1.1 400 Bad Request');
    _syslog("badreq:" . $text);
    die($text);
}

function remoteerror($text) {
    header('HTTP/1.1 421 Misdirected Request');
    _syslog("remote_err:" . $text);
    die($text);
}

function httpok($text) {
    header('HTTP/1.1 200 OK');
    _syslog("ok:" . $text);
    echo($text);
    exit(0);
}

function accepted() {
    header('HTTP/1.1 202 Accepted');
    _syslog("accepted:");
    exit(0);
}

function verify_token($token) {
    $request = curl_init();
    curl_setopt($request, CURLOPT_URL, 'https://tokens.indieauth.com/token');
    curl_setopt($request, CURLOPT_HTTPHEADER, array(
        'Content-Type: application/x-www-form-urlencoded',
        "Authorization: Bearer {$token}"
    ));
    curl_setopt($request, CURLOPT_RETURNTRANSFER, 1);
    $response = curl_exec($request);
    curl_close($request);
    parse_str(urldecode($response), $verification);

    if (! isset($verification['scope']) ) {
        unauthorized('missing "scope"');
    }
    if (! isset($verification['me']) ) {
        unauthorized('missing "me"');
    }
    if ( ! stristr($verification['me'], '{{ site.name }}') ) {
        unauthorized('wrong domain');
    }
}

function save_to_wallabag($url) {
    $wallabag_url = "{{ wallabag["url"] }}";
    $data = array(
        "client_id" => "{{ wallabag["client_id"] }}",
        "client_secret" => "{{ wallabag["client_secret"] }}",
        "username" => "{{ wallabag["username"] }}",
        "password" => "{{ wallabag["password"] }}",
        "grant_type" => "password"
    );

    $request = curl_init();
    curl_setopt($request, CURLOPT_URL, "{$wallabag_url}/oauth/v2/token");
    curl_setopt($request, CURLOPT_POST, 1);
    curl_setopt($request, CURLOPT_POSTFIELDS,http_build_query($data));
    curl_setopt($request, CURLOPT_RETURNTRANSFER, 1);
    $response = curl_exec($request);
    curl_close($request);

    try {
        $wallabag_token = json_decode($response, true);
    } catch (Exception $e) {
        remoteerror("failed to parse response from wallabag: " . $response);
    }

    if (! isset($wallabag_token['access_token']) ) {
        remoteerror("failed to obtain access token from wallabag: " . $response);
    }

    $data = array(
        "url" => $url,
        "archive" => 1
    );
    $headers = array(
        'Content-Type: application/x-www-form-urlencoded',
        "Authorization: Bearer ". $wallabag_token["access_token"]
    );
    $request = curl_init();
    curl_setopt($request, CURLOPT_URL, "{$wallabag_url}/api/entries");
    curl_setopt($request, CURLOPT_POST, 1);
    curl_setopt($request, CURLOPT_POSTFIELDS,http_build_query($data));
    curl_setopt($request, CURLOPT_HTTPHEADER, $headers);
    curl_setopt($request, CURLOPT_RETURNTRANSFER, 1);
    $response = curl_exec($request);
    curl_close($request);
    try {
        $is_saved = json_decode($response, true);
        accepted();
    } catch (Exception $e) {
        remoteerror("failed to parse response to save from wallabag: " . $response);
    }
}

function maybe_array_pop($x) {
    if(is_array($x)) {
        return array_pop($x);
    }
    else {
        return $x;
    }
}

if (!empty($_GET)) {
    if ( ! isset($_GET['q']) ) {
        badrequest('please POST a micropub request');
    }
    if ( isset($_GET['q']['config']) ) {
        httpok('{{tags|tojson(indent=4)}}');
    }
    if(isset($_GET['q']['syndicate-to'])) {
        httpok(json_encode(array('syndicate-to' => array())));
    }
    badrequest('please POST a micropub request');
}

$raw = file_get_contents("php://input");
$decoded = 'null';
try {
    $decoded = json_decode($raw, true);
} catch (Exception $e) {
    _syslog('failed to decode JSON, trying decoding form data');
}
if($decoded == 'null' or empty($decoded)) {
    try {
        parse_str($raw, $decoded);
    }
    catch (Exception $e) {
        _syslog('failed to decoding form data as well');
        badrequest('invalid POST contents');
    }
}

$token = '';
if (isset($decoded['access_token'])) {
    $token = $decoded['access_token'];
    unset($decoded['access_token']);
}
elseif (isset($_SERVER['HTTP_AUTHORIZATION'])) {
    $token = trim(str_replace('Bearer', '', $_SERVER['HTTP_AUTHORIZATION']));
}

if (empty($token)) {
    unauthorized('missing token');
}
else {
    verify_token($token);
}

/* likes and bookmarks */
$bookmark_url = '';
if(isset($decoded["properties"]) && isset($decoded["properties"]["like-of"])) {
    $bookmark_url = maybe_array_pop($decoded["properties"]["like-of"]);
}
elseif(isset($decoded["like-of"])) {
    $bookmark_url = maybe_array_pop($decoded["like-of"]);
}

if(!empty($bookmark_url)) {
    save_to_wallabag($bookmark_url);
    accepted();
}
else {
    /* save everything else into the queue for now */
    $t = microtime(true);
    $fpath = "/web/petermolnar.net/queue/{$t}.json";
    if(!is_dir(dirname($fpath))) {
        mkdir(dirname($fpath), 0755, true);
    }
    $c = json_encode($decoded, JSON_PRETTY_PRINT);
    if (file_put_contents($fpath, $c)) {
        accepted();
    }
}

/* fallback to not implemented */
notimplemented();
