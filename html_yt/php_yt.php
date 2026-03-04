<?php
// 检查是否有 POST 数据
if ($_SERVER["REQUEST_METHOD"] == "POST") {
    // 获取输入的姓名
    $name = htmlspecialchars($_POST["name"]);
    
    // 显示结果
    echo "<h2>您输入的姓名是: " . $name . "</h2>";
} else {
    echo "请通过表单提交数据。";
}
?>