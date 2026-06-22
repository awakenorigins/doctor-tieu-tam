# Error Patterns → Root Cause → Fix

| Pattern / triệu chứng | Loại | Nguyên nhân gốc thường gặp | Hướng chữa |
|---|---|---|---|
| "Codex usage limit" dù đã chọn model khác | Config | thiếu agentRuntime, chạy nhầm harness | set agentRuntime openclaw |
| curl /health fail, connection refused | Env | service/port down hoặc bind sai interface | start service / bind 0.0.0.0 |
| 401 invalid api key | Config/Secret | key sai/hết hạn | đổi key đúng (không log ra chat) |
| 403 Cloudflare "Just a moment" | External | bị bot-protection chặn | dùng phiên browser thật / OAuth callback |
| timeout khi gọi model | Transient/External | upstream chậm/down | retry, tăng timeoutSeconds |
| gateway not reachable | Env | gateway crash / config JSON hỏng | restore backup, restart |
| port bind chỉ Tailscale IP | Env | HOST=100.x thay vì 0.0.0.0 | đổi bind 0.0.0.0 |
| service chết sau reboot | Env | không có auto-restart | systemd/scheduled task + StartLimit chống loop |
| SSH: key not accessible | Local | sai đường dẫn key | trỏ đúng path key |
| PowerShell qua SSH lỗi quoting | Local | shell ăn ký tự | dùng -EncodedCommand (base64 UTF-16LE) |

## Phân loại lỗi
- **Transient:** mạng/timeout/rate-limit → retry.
- **Environmental:** file/port/permission/service → sửa môi trường.
- **Config:** sai key cấu hình → sửa config + restart.
- **External:** API đổi/dịch vụ down → adapt/chờ.
- **Secret/Auth:** ESCALATE, không tự đổi credential khi chưa được phép.
