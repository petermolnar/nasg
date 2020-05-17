<?php

const baseurl = '{{ site.url }}';

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

if(isset($_GET['q'])) {
    $q = $_GET['q'];
}
elseif(isset($_GET['search'])) {
    $q = $_GET['search'];
}
else {
    $q = '';
}
$q = filter_var($q, FILTER_SANITIZE_STRING);
$db = new SQLite3('./search.sqlite', SQLITE3_OPEN_READONLY);
$sql = $db->prepare("
    SELECT
        url, category, title, snippet(data, '', '', '[...]', 5, 24), mtime
    FROM
        data
    WHERE
        data MATCH :q
    ORDER BY
        category, mtime
");
$sql->bindValue(':q', str_replace('-', '+', $q));
$query = $sql->execute();
$results = array();
if($query) {
    while ($row = $query->fetchArray(SQLITE3_ASSOC)) {
        $item = array(
            "id" => $row['url'],
            "title" => $row['title'],
            "url" => $row['url'],
            "description" => $row["snippet(data, '', '', '[...]', 5, 24)"],
            "pubDate" => gmdate(DATE_RFC2822, $row['mtime']),
        );
        array_push($results, $item);
    }
}

if (isset($_GET['xml'])) {
    header('Content-Type: text/xml; charset=utf-8', true);

    $xml = new DOMDocument("1.0", "UTF-8");
    $xml->preserveWhiteSpace = false;
    $xml->formatOutput = true;

    $rss = $xml->createElement("rss");
    $rss_node = $xml->appendChild($rss);
    $rss_node->setAttribute("version","2.0");

    $rss_node->setAttribute("xmlns:dc","http://a9.com/-/spec/opensearch/1.1/");

    $channel = $xml->createElement("channel");
    $channel_node = $rss_node->appendChild($channel);

    $channel_node->appendChild($xml->createElement("title", "Search results for: {$_GET['q']}"));
    $channel_node->appendChild($xml->createElement("link", "{{ site.url }}"));
    $channel_node->appendChild($xml->createElement("description", "Search {{ site.name }} for {$_GET['q']}"));

    $channel_node->appendChild($xml->createElement("openSearch:totalResults", sizeof($results)));
    $channel_node->appendChild($xml->createElement("openSearch:startIndex", 1));
    $channel_node->appendChild($xml->createElement("openSearch:itemsPerPage", sizeof($results)));

    $build_date = gmdate(DATE_RFC2822, time());
    $channel_node->appendChild($xml->createElement("lastBuildDate", $build_date));

    foreach ($results as $row) {
        $item_node = $channel_node->appendChild($xml->createElement("item"));
        $title_node = $item_node->appendChild($xml->createElement("title", $row['title']));
        $link_node = $item_node->appendChild($xml->createElement("link", $row['url']));
        $guid_link = $xml->createElement("guid", $row['url']);
        $guid_link->setAttribute("isPermaLink","false");
        $guid_node = $item_node->appendChild($guid_link);
        $description_node = $item_node->appendChild($xml->createElement("description"));
        $description_contents = $xml->createCDATASection(htmlentities($row["description"]));
        $description_node->appendChild($description_contents);
        $pub_date = $xml->createElement("pubDate", $row['pubDate']);
        $pub_date_node = $item_node->appendChild($pub_date);
    }

    echo $xml->saveXML();
    exit(0);
}

if (isset($_GET['json'])) {
    // WordPress JSON
    header('Content-Type: application/json; charset=utf-8', true);
    echo(json_encode($results));
    exit(0);
}

?>

{% extends "base.j2.html" %}
{% block lang %}{% endblock %}
{% block title %}Search results for: <?php echo($q); ?>{% endblock %}
{% block content %}

<div id="main" class="h-feed hatom main">
    <h1>Search results for: <?php echo($q); ?></h1>
    <dl>
<?php
    foreach($results as $row) {
        printf('<dt><a href="%s">%s</a></dt><dd>%s</dd>', relurl(baseurl, $row['url']), $row['title'], $row["description"]);
    }
?>
    </dl>
</div>
{% endblock %}
