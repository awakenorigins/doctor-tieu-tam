---
name: doctor-tieu-tam
description: "Bác sĩ heal từ xa cho PC và OpenClaw khác. Dùng khi một máy/agent OpenClaw (qua Tailscale/SSH) báo lỗi, không reply, sai config model/provider, gateway chết, port proxy down, cron/subagent fail, hoặc cần chẩn đoán + sửa từ xa. Quy trình: kết nối an toàn → khám sức khỏe → đọc log → chẩn đoán nguyên nhân gốc → backup → fix → verify → ghi known-fixes → báo cáo. Triggers: heal PC, sửa openclaw từ xa, máy không reply, gateway down, model swap không chạy, codex limit nhưng đã chọn claude, ssh fix, tailscale fix, doctor, chẩn đoán lỗi máy khác."
---

# Doctor Tiểu Tâm

Bác sĩ chẩn đoán + chữa từ xa cho PC và các instance OpenClaw khác qua Tailscale/SSH. Lấy cảm hứng cấu trúc từ `psyduckler/self-healing-agents` (Detect→Triage→Diagnose→Fix→Verify→Log) + bộ đồ nghề sysadmin + quy trình SSH remote heal thực chiến.

## Triết lý

Không phải "báo lỗi rồi chờ người". Là: **kết nối → khám → chẩn đoán gốc → backup → fix → verify → học**. Mỗi ca bệnh chữa xong ghi vào `known-fixes.json` để lần sau nhanh hơn.

## Nguyên tắc an toàn (BẮT BUỘC đọc trước khi chữa)

1. **Không tự ý đăng nhập máy người khác khi chưa có credential do chủ máy cấp.** SSH key / token phải do chủ máy add.
2. **Luôn backup trước khi sửa config.** Copy `*.bak-tt-<timestamp>` trước mọi thay đổi.
3. **Không clobber cả file bằng one-liner.** Đọc → merge → ghi. Giữ nguyên phần không liên quan.
4. **Verify bằng bằng chứng thật** (curl 200, log thấy request, service Running), không "tin là đã fix".
5. **Escalate khi:** đụng đổi credential/API key, nguy cơ mất dữ liệu, đã fix mà fail, fix đổi hành vi người dùng, nhiều lỗi đồng thời.
6. **Token/secret KHÔNG bao giờ in ra chat.** Set qua env/file trên server.

## Kết nối từ xa (Connect)

### Tailscale (ưu tiên)
```bash
tailscale status                     # liệt kê node, IP 100.x
tailscale ping <ip>                  # kiểm tra reachability
```

### SSH (sau khi chủ máy add public key)
- Tạo key riêng cho việc heal:
```bash
ssh-keygen -t ed25519 -N '' -C 'doctor-tieu-tam' -f ~/.ssh/doctor_tt
cat ~/.ssh/doctor_tt.pub   # đưa chủ máy add
```
- Windows: user thường → `~/.ssh/authorized_keys`; user admin → `C:\ProgramData\ssh\administrators_authorized_keys` + ACL chỉ Administrators/SYSTEM.
- Linux/mac: `~/.ssh/authorized_keys`.
- Kết nối:
```bash
ssh -i ~/.ssh/doctor_tt -o StrictHostKeyChecking=accept-new <user>@<ip> "whoami"
```

## Quy trình chữa bệnh

### B1. Detect — phát hiện
```bash
python3 <skill-dir>/scripts/doctor.py scan --target <user>@<ip>
```
Thu thập: OS, service OpenClaw/gateway state, port quan trọng, disk/RAM, lỗi gần đây.

### B2. Healthcheck — khám sức khỏe
```bash
python3 <skill-dir>/scripts/doctor.py health --target <user>@<ip>
```
Kiểm CPU/RAM/disk, port lắng nghe, gateway reachable, proxy/API endpoint.

### B3. Diagnose — chẩn đoán
1. Check known-fixes trước: `python3 <skill-dir>/scripts/doctor.py check "<triệu chứng>"`
2. Đọc log/lỗi → trace tới nguồn (config / port / runtime / credential / mạng).
3. Phân loại: Transient | Environmental | Config | Code | External.
   - Xem `references/openclaw-playbook.md` cho ca OpenClaw đặc thù (model swap không chạy, gateway down, proxy bind sai, runtime sai...).

### B4. Backup + Fix
- Luôn backup file trước.
- Ưu tiên fix gốc (heal) hơn vá tạm (patch) hơn retry.
- Config OpenClaw: đọc → sửa đúng key → ghi → restart/reload.

### B5. Verify
```bash
python3 <skill-dir>/scripts/doctor.py verify --target <user>@<ip>
```
Re-run thao tác lỗi, check 200/Running/log thấy request. Fail → revert + escalate.

### B6. Log — ghi known-fixes
```bash
python3 <skill-dir>/scripts/doctor.py log \
  --symptom "<triệu chứng>" --cause "<nguyên nhân gốc>" \
  --fix "<đã làm gì>" --fix-type "retry|patch|heal" --target "<máy>"
```
Ghi vào `known-fixes.json` (workspace root).

## Heartbeat (tuỳ chọn)
Thêm vào HEARTBEAT.md nếu cần giám sát chủ động các máy đã đăng ký trong `references/fleet.md`:
- Mỗi vài giờ: `doctor.py health --target ...` cho từng máy → chỉ báo khi có bất thường, KHÔNG spam.

## Files
- `scripts/doctor.py` — CLI: scan / health / check / verify / log / connect-test
- `scripts/openclaw_heal.py` — helpers chữa OpenClaw từ xa (đọc/sửa config, restart gateway)
- `references/openclaw-playbook.md` — playbook ca bệnh OpenClaw thường gặp
- `references/error-patterns.md` — mẫu lỗi → nguyên nhân → cách chữa
- `known-fixes.json` — DB học được (tạo ở workspace root lần chạy đầu)
