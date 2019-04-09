<?php

function _syslog($msg) {
    $trace = debug_backtrace();
    $caller = $trace[1];
    $parent = $caller['function'];
    if (isset($caller['class']))
        $parent = $caller['class'] . '::' . $parent;

    return error_log( "{$parent}: {$msg}" );
}

function unauthorized($text) {
    header('HTTP/1.1 401 Unauthorized');
    die($text);
}

function badrequest($text) {
    header('HTTP/1.1 400 Bad Request');
    die($text);
}

function httpok($text) {
    header('HTTP/1.1 200 OK');
    echo($text);
    exit(0);
}

function accepted() {
    header('HTTP/1.1 202 Accepted');
    #header('Location: https://petermolnar.net');
    exit(0);
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
print_r($raw);
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
print_r($decoded);

$token = '';
if ( isset($decoded['access_token']) ) {
    $token = $decoded['access_token'];
    unset($decoded['access_token']);
}
elseif ( isset($_SERVER['HTTP_AUTHORIZATION']) ) {
    $token = trim(str_replace('Bearer', '', $_SERVER['HTTP_AUTHORIZATION']));
}

if (empty($token)) {
    unauthorized('missing token');
}

$request = curl_init();
curl_setopt($request, CURLOPT_URL, 'https://tokens.indieauth.com/token');
curl_setopt($request, CURLOPT_HTTPHEADER, array(
    'Content-Type: application/x-www-form-urlencoded',
    sprintf('Authorization: Bearer %s', $token)
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
if ( ! stristr($verification['me'], 'https://petermolnar.net') ) {
    unauthorized('wrong domain');
}
if ( ! stristr($verification['scope'], 'create') ) {
    unauthorized('invalid scope');
}

$user = posix_getpwuid(posix_getuid());
$now = time();
$decoded['mtime'] = $now;
$fname = sprintf(
    '%s/%s/%s.json',
    $user['dir'],
    'queue',
    microtime(true)
);

file_put_contents($fname, json_encode($decoded, JSON_PRETTY_PRINT));
accepted();