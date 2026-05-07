<?php
// MediAI — API: Medication Schedule
require_once '../includes/config.php';

header('Access-Control-Allow-Origin: *');
header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { exit(0); }

$db = getDB();

function requestData(): array {
    $contentType = $_SERVER['CONTENT_TYPE'] ?? '';
    if (stripos($contentType, 'application/json') !== false) {
        return json_decode(file_get_contents('php://input'), true) ?? [];
    }
    return $_POST;
}

function normalizeFrequency(string $value): string {
    $value = strtolower(trim($value));
    $value = str_replace(['-', ' '], '_', $value);
    $map = [
        'once_daily' => 'once_daily',
        'once_a_day' => 'once_daily',
        'daily' => 'once_daily',
        'od' => 'once_daily',
        'twice_daily' => 'twice_daily',
        'twice_a_day' => 'twice_daily',
        'two_times_daily' => 'twice_daily',
        'bid' => 'twice_daily',
        'three_times' => 'three_times',
        'three_times_daily' => 'three_times',
        'three_times_a_day' => 'three_times',
        'tid' => 'three_times',
        'four_times' => 'four_times',
        'four_times_daily' => 'four_times',
        'qid' => 'four_times',
        'every_8h' => 'every_8h',
        'every_8_hours' => 'every_8h',
        'q8h' => 'every_8h',
        'every_6h' => 'every_6h',
        'every_6_hours' => 'every_6h',
        'q6h' => 'every_6h',
        'as_needed' => 'as_needed',
        'prn' => 'as_needed',
        'weekly' => 'weekly',
    ];
    if (isset($map[$value])) {
        return $map[$value];
    }
    if (strpos($value, 'twice') !== false || strpos($value, '2') !== false) return 'twice_daily';
    if (strpos($value, 'three') !== false || strpos($value, '3') !== false) return 'three_times';
    if (strpos($value, 'four') !== false || strpos($value, '4') !== false) return 'four_times';
    if (strpos($value, '8') !== false) return 'every_8h';
    if (strpos($value, '6') !== false) return 'every_6h';
    if (strpos($value, 'need') !== false || strpos($value, 'prn') !== false) return 'as_needed';
    if (strpos($value, 'week') !== false) return 'weekly';
    return 'once_daily';
}

function insertMedication(PDO $db, array $data): int {
    $user_id      = (int)($data['user_id'] ?? 0);
    $doc_id       = (int)($data['document_id'] ?? 0);
    $medicine     = sanitize($data['medicine_name'] ?? $data['name'] ?? '');
    $dosage       = sanitize($data['dosage'] ?? '');
    $frequency    = normalizeFrequency((string)($data['frequency'] ?? 'once_daily'));
    $start_date   = sanitize($data['start_date'] ?? date('Y-m-d'));
    $end_date     = sanitize($data['end_date'] ?? '');
    $instructions = sanitize($data['instructions'] ?? '');
    $duration     = sanitize($data['duration'] ?? '');
    $route        = sanitize($data['route'] ?? '');

    $notes = trim(implode(' ', array_filter([
        $route ? 'Route: ' . $route . '.' : '',
        $duration ? 'Duration: ' . $duration . '.' : '',
        $instructions,
    ])));

    if (!$user_id || !$medicine) {
        return 0;
    }

    $stmt = $db->prepare('INSERT INTO medication_schedule
        (user_id, document_id, medicine_name, dosage, frequency, start_date, end_date, instructions, active, created_at)
        VALUES (?,?,?,?,?,?,?,?,1,NOW())');
    $stmt->execute([$user_id, $doc_id ?: null, $medicine, $dosage, $frequency, $start_date, $end_date ?: null, $notes]);

    return (int)$db->lastInsertId();
}

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $user_id = (int)($_GET['user_id'] ?? 0);
    if (!$user_id) { jsonResponse(['success'=>false,'message'=>'user_id required']); }
    $stmt = $db->prepare('
        SELECT m.*, d.original_name AS document_name
        FROM medication_schedule m
        LEFT JOIN medical_documents d ON m.document_id = d.id
        WHERE m.user_id=? AND m.active=1
        ORDER BY m.created_at DESC
    ');
    $stmt->execute([$user_id]);
    jsonResponse(['success'=>true, 'medications'=>$stmt->fetchAll()]);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $data = requestData();
    if (isset($data['medications']) && is_array($data['medications'])) {
        $ids = [];
        foreach ($data['medications'] as $med) {
            if (!is_array($med)) continue;
            $med['user_id'] = $data['user_id'] ?? ($med['user_id'] ?? 0);
            $med['document_id'] = $data['document_id'] ?? ($med['document_id'] ?? 0);
            $id = insertMedication($db, $med);
            if ($id) $ids[] = $id;
        }
        jsonResponse(['success'=>count($ids) > 0, 'medication_ids'=>$ids, 'count'=>count($ids)]);
    }

    $id = insertMedication($db, $data);
    if (!$id) { jsonResponse(['success'=>false,'message'=>'user_id and medicine_name required']); }

    jsonResponse(['success'=>true, 'medication_id'=>$id]);
}

if ($_SERVER['REQUEST_METHOD'] === 'PUT') {
    $data = json_decode(file_get_contents('php://input'), true) ?? [];
    $id = (int)($data['id'] ?? 0);
    $user_id = (int)($data['user_id'] ?? 0);
    if (!$id || !$user_id) { jsonResponse(['success'=>false,'message'=>'id and user_id required']); }

    $stmt = $db->prepare('UPDATE medication_schedule
        SET medicine_name=?, dosage=?, frequency=?, start_date=?, end_date=?, instructions=?
        WHERE id=? AND user_id=?');
    $stmt->execute([
        sanitize($data['medicine_name'] ?? ''),
        sanitize($data['dosage'] ?? ''),
        normalizeFrequency((string)($data['frequency'] ?? 'once_daily')),
        sanitize($data['start_date'] ?? date('Y-m-d')),
        sanitize($data['end_date'] ?? '') ?: null,
        sanitize($data['instructions'] ?? ''),
        $id,
        $user_id
    ]);
    jsonResponse(['success'=>true]);
}

if ($_SERVER['REQUEST_METHOD'] === 'DELETE') {
    $data = json_decode(file_get_contents('php://input'), true) ?? [];
    $id   = (int)($data['id'] ?? 0);
    $user_id = (int)($data['user_id'] ?? 0);
    if (!$id) { jsonResponse(['success'=>false,'message'=>'id required']); }
    if ($user_id) {
        $db->prepare('UPDATE medication_schedule SET active=0 WHERE id=? AND user_id=?')->execute([$id, $user_id]);
    } else {
        $db->prepare('UPDATE medication_schedule SET active=0 WHERE id=?')->execute([$id]);
    }
    jsonResponse(['success'=>true]);
}
