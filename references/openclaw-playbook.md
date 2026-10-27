# OpenClaw Remote Heal Playbook

Các ca bệnh OpenClaw thường gặp khi heal từ xa, kèm nguyên nhân gốc + cách chữa đã kiểm chứng.

## Ca 1: Set model Claude/provider khác nhưng vẫn báo "Codex usage limit"
**Triệu chứng:** `/model claudekkg/...` báo "Model set" nhưng khi chat lại báo Codex limit; log proxy KHÔNG thấy request.
**Nguyên nhân gốc:** provider/model thiếu `agentRuntime` → OpenClaw chạy bằng harness Codex thay vì runtime HTTP, nên không gọi API provider.
**Chữa:** set `agentRuntime.id = "openclaw"` ở:
1. cấp provider: `models.providers.<prov>.agentRuntime`
2. từng model: `agents.defaults.models["<prov>/<model>"].agentRuntime`
Backup → ghi config → restart gateway → verify log proxy thấy request.
**Tool:** `openclaw_heal.py set-runtime --provider <prov> --runtime openclaw`

## Ca 2: Bot/máy không reply
**Kiểm tra theo thứ tự:**
1. Gateway còn sống? (scheduled task / systemd state)
2. Channel (telegram) còn token đúng? bot bị revoke?
3. Model primary trỏ vào provider chết? → fallback chain cạn?
4. Proxy/API upstream down? (port không listen)

## Ca 3: Proxy/API "add xong không dùng được"
**Nguyên nhân hay gặp:**
- Proxy bind chỉ vào 1 interface (vd Tailscale IP) → client interface khác fail. Fix: bind `0.0.0.0`.
- Service chết sau restart máy. Fix: tạo systemd/scheduled-task auto-restart có giới hạn (StartLimitBurst) chống loop.
- Client trong/ngoài Tailscale dùng sai base URL.
**Verify:** `curl <base>/health` từ chính máy client.

## Ca 4: Gateway down sau update/restart
1. Đọc log gateway.
2. Config JSON hỏng (lỗi cú pháp) → khôi phục từ `*.bak-tt-*`.
3. Port bị chiếm → đổi/po kill tiến trình cũ.
4. Restart, verify state Running + health endpoint.

## Quy tắc fix config từ xa
- LUÔN backup `*.bak-tt-<timestamp>` trước.
- Đọc JSON → sửa key trong Python → ghi lại (KHÔNG one-liner clobber).
- Giữ nguyên primary/secret nếu user không yêu cầu đổi.
- Verify bằng bằng chứng thật.
