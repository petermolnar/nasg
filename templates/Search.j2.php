{% extends "base.j2.html" %}
{% block lang %}{% endblock %}
{% block title %}Search results for: <?php echo($_GET['q']); ?>{% endblock %}
{% block content %}
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
<?php const baseurl = '{{ site.url }}'; ?>
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
{% endblock %}
