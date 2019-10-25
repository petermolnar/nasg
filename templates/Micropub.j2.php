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

if (!empty($_GET)) {
    if ( ! isset($_GET['q']) ) {
        badrequest('please POST a micropub request');
    }
    if ( isset($_GET['q']['config']) ) {
        httpok(json_encode(array('tags' => array())));
    }
    if(isset($_GET['q']['syndicate-to'])) {
        httpok(json_encode(array('syndicate-to' => array())));
    }
    badrequest('please POST a micropub request');
}


$raw = file_get_contents("php://input");
try {
    $decoded = json_decode($raw, true);
} catch (Exception $e) {
    _syslog('failed to decode JSON, trying decoding form data');
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

$source_url = '';
if(isset($decoded["properties"]) && isset($decoded["properties"]["like-of"])) {
    $source_url = $decoded["properties"]["like-of"];
}
elseif(isset($decoded["like-of"])) {
    $source_url = $decoded["like-of"];
}

/* deal with like: forward it to wallabag */
if(!empty($source_url)) {
    save_to_wallabag($source_url);
}

notimplemented();
