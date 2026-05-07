<?php
// MediAI — API: Document Upload
require_once '../includes/config.php';

header('Access-Control-Allow-Origin: *');
header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { exit(0); }

$db = getDB();

function decodeAnalysisRows(array $rows): array {
    foreach ($rows as &$row) {
        $row['ai_analysis'] = !empty($row['ai_analysis']) ? json_decode($row['ai_analysis'], true) : null;
    }
    return $rows;
}

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $user_id = (int)($_GET['user_id'] ?? 0);
    if (!$user_id) { jsonResponse(['success'=>false,'message'=>'user_id required']); }
    $document_id = (int)($_GET['id'] ?? 0);
    if ($document_id) {
        $stmt = $db->prepare('
            SELECT id, original_name, stored_name, file_path, document_type, file_size, mime_type, ai_analysis, uploaded_at
            FROM medical_documents
            WHERE user_id=? AND id=?
            LIMIT 1
        ');
        $stmt->execute([$user_id, $document_id]);
        $rows = decodeAnalysisRows($stmt->fetchAll());
        jsonResponse(['success'=>true, 'document'=>$rows[0] ?? null]);
    }

    $stmt = $db->prepare('
        SELECT id, original_name, stored_name, file_path, document_type, file_size, mime_type, ai_analysis, uploaded_at
        FROM medical_documents
        WHERE user_id=?
        ORDER BY uploaded_at DESC
    ');
    $stmt->execute([$user_id]);
    jsonResponse(['success'=>true, 'documents'=>decodeAnalysisRows($stmt->fetchAll())]);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $user_id = (int)($_POST['user_id'] ?? 0);
    if (!$user_id) { jsonResponse(['success'=>false,'message'=>'user_id required']); }

    if (!isset($_FILES['document']) || $_FILES['document']['error'] !== UPLOAD_ERR_OK) {
        jsonResponse(['success'=>false,'message'=>'No file uploaded or upload error']);
    }

    $file = $_FILES['document'];
    $allowed = ['application/pdf','application/x-pdf','image/jpeg','image/jpg','image/png'];
    $finfo = finfo_open(FILEINFO_MIME_TYPE);
    $mime = finfo_file($finfo, $file['tmp_name']);
    finfo_close($finfo);

    if (!in_array($mime, $allowed)) {
        jsonResponse(['success'=>false,'message'=>'Invalid file type. Only PDF, JPG, PNG allowed.']);
    }
    if ($file['size'] > 15 * 1024 * 1024) {
        jsonResponse(['success'=>false,'message'=>'File too large. Maximum 15MB.']);
    }

    $uploadDir = __DIR__ . '/../uploads/';
    if (!is_dir($uploadDir)) { mkdir($uploadDir, 0755, true); }

    $ext      = pathinfo($file['name'], PATHINFO_EXTENSION);
    $filename = 'doc_' . $user_id . '_' . time() . '_' . bin2hex(random_bytes(4)) . '.' . $ext;
    $destPath = $uploadDir . $filename;

    if (!move_uploaded_file($file['tmp_name'], $destPath)) {
        jsonResponse(['success'=>false,'message'=>'Failed to save file']);
    }

    $stmt = $db->prepare('INSERT INTO medical_documents
        (user_id, original_name, stored_name, file_path, file_size, mime_type, uploaded_at)
        VALUES (?,?,?,?,?,?,NOW())');
    $stmt->execute([$user_id, $file['name'], $filename, 'uploads/'.$filename, $file['size'], $mime]);
    $docId = (int)$db->lastInsertId();

    jsonResponse([
        'success' => true,
        'id'      => $docId,
        'path'    => 'uploads/' . $filename,
        'name'    => $file['name']
    ]);
}

if ($_SERVER['REQUEST_METHOD'] === 'PUT') {
    $data = json_decode(file_get_contents('php://input'), true) ?? [];
    $id = (int)($data['id'] ?? 0);
    $documentType = sanitize($data['document_type'] ?? 'Unknown');
    $analysis = $data['ai_analysis'] ?? null;

    if (!$id) {
        jsonResponse(['success'=>false,'message'=>'id required'], 400);
    }

    $stmt = $db->prepare('UPDATE medical_documents SET document_type=?, ai_analysis=? WHERE id=?');
    $stmt->execute([
        $documentType ?: 'Unknown',
        $analysis !== null ? json_encode($analysis) : null,
        $id
    ]);

    jsonResponse(['success'=>true]);
}

if ($_SERVER['REQUEST_METHOD'] === 'DELETE') {
    $data = json_decode(file_get_contents('php://input'), true) ?? [];
    $id = (int)($data['id'] ?? 0);
    $user_id = (int)($data['user_id'] ?? 0);

    if (!$id || !$user_id) {
        jsonResponse(['success'=>false,'message'=>'id and user_id required'], 400);
    }

    $stmt = $db->prepare('SELECT file_path FROM medical_documents WHERE id=? AND user_id=? LIMIT 1');
    $stmt->execute([$id, $user_id]);
    $doc = $stmt->fetch();
    if (!$doc) {
        jsonResponse(['success'=>false,'message'=>'Document not found'], 404);
    }

    $uploadRoot = realpath(__DIR__ . '/../uploads');
    $fullPath = realpath(__DIR__ . '/../' . $doc['file_path']);
    if ($uploadRoot && $fullPath && strpos($fullPath, $uploadRoot . DIRECTORY_SEPARATOR) === 0 && is_file($fullPath)) {
        unlink($fullPath);
    }

    $db->prepare('DELETE FROM medical_documents WHERE id=? AND user_id=?')->execute([$id, $user_id]);
    jsonResponse(['success'=>true]);
}

jsonResponse(['success'=>false,'message'=>'Method not allowed'], 405);
