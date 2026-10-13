# Phân tích lỗi theo ngữ cảnh

Phân tích do trợ lý thực hiện ngày 2026-10-13 từ `test_predictions.csv` và mẫu lỗi confidence cao
trong `error_review.csv`. Đây là nhận xét chẩn đoán, không phải nhãn nguyên nhân đã được chuyên gia
xác nhận. Không chỉnh sửa nhãn test và không điền hộ phần tự đánh giá của người học.

## Kết luận định lượng

- PhoBERT tăng **0,022069 Macro-F1** so với baseline, nhưng thấp hơn validation **0,029761**.
- OFFENSIVE là lớp khó nhất: precision 0,3789, recall 0,4617, F1 0,4162. Trong 444 mẫu,
  170 bị đoán CLEAN và 69 bị đoán HATE. Đồng thời 234 CLEAN và 102 HATE bị đoán OFFENSIVE.
- HATE: 397/688 mẫu đúng; 189 bị bỏ lọt thành CLEAN và 102 bị hạ xuống OFFENSIVE.
  Accuracy chung 86,47% che khuất một phần lỗi ở hai lớp ít mẫu hơn CLEAN.
  Baseline nhận đúng 433/688 HATE (recall 0,6294), cao hơn PhoBERT 0,5770: cải thiện
  Macro-F1/accuracy chung không đồng nghĩa tốt hơn trên mọi tiêu chí.
- Có 95 dòng test overlap với validation theo chuẩn hóa Stage 1. Bỏ nhóm này để phân tích
  độ nhạy cho Macro-F1 0,6536 trên 6.585 dòng, gần điểm chính 0,6546; điều này không loại trừ
  near-duplicates hoặc mọi dạng phụ thuộc giữa các tập.
- Chỉ 3/6.680 dòng vượt 128 token, trong đó 1 lỗi. Truncation không thể giải thích phần lớn
  904 lỗi trong lần chạy này. Nhóm 33–128 token có 97/458 lỗi, so với 806/6.219 ở nhóm ≤32;
  chưa thể quy kết quan hệ nhân quả vì phân bố nhãn và nội dung các nhóm khác nhau.

## Ví dụ cụ thể

| Row ID | Nhãn thật → dự đoán | Quan sát từ văn bản | Hướng kiểm tra |
|---|---|---|---|
| `test:6205` | OFFENSIVE → CLEAN | “Top1 ca sĩ nhưng k biết hát :))” thể hiện chê bai qua đối lập, viết tắt và emoticon; không cần từ tục để mang ý xúc phạm. | Khả năng nhận diện công kích gián tiếp/mỉa mai. Không đủ bằng chứng để khẳng định chính emoticon gây lỗi. |
| `test:1556` | OFFENSIVE → CLEAN | Kéo dài ký tự trong “chưaaa” và biến thể viết kéo dài của từ tục. | Độ bền với cách viết biến thể; chỉ thử chuẩn hóa/augmentation trên train và validation ở nghiên cứu sau. |
| `test:3327` | HATE → CLEAN | Câu giới thiệu có cụm “Cao Thất Đức”, có thể chứa chơi chữ/công kích một người. | Cần ngữ cảnh đối tượng và hướng dẫn nhãn để giải thích ranh giới HATE. Không tự suy ra nhãn sai. |
| `test:3960` | CLEAN → OFFENSIVE | “Sự lươn lẹo là vậy” được dữ liệu gán CLEAN dù có từ đánh giá tiêu cực. | Phân biệt đánh giá tiêu cực với xúc phạm trong ngữ cảnh; model có thể dựa quá nhiều vào từ tiêu cực, đây mới là giả thuyết. |
| `test:4257` | CLEAN → HATE | Câu dài vừa kể lại một clip vừa có các cụm đánh giá gay gắt. | Cần phân biệt trích dẫn/kể lại, nhận xét và công kích; nhãn CLEAN trong dữ liệu không tự động được coi là lỗi annotation. |
| `test:2856` | OFFENSIVE → HATE | Lời chê một “quan điểm” kèm từ tục. | Ranh giới mục tiêu bị công kích và mức độ xúc phạm; không đồng nhất có từ tục với HATE. |
| `test:6002` | HATE → OFFENSIVE | “Xạo l” rất ngắn, viết tắt, thiếu đối tượng trong câu. | Bổ sung ngữ cảnh hội thoại nếu nguồn dữ liệu cho phép; không đủ thông tin trong một câu để xác nhận nguyên nhân. |
| `test:5800` | HATE → OFFENSIVE | Có cách gọi miệt thị gắn với xu hướng tính dục. | Kiểm tra khả năng nhận diện công kích nhóm/đặc điểm cá nhân theo hướng dẫn gán nhãn. |

Các ví dụ được chọn có chủ đích để minh họa, không dùng để ước lượng tần suất từng nguyên nhân.
Chưa có double annotation hoặc đo agreement giữa người đánh giá.

## Đề xuất nghiên cứu tiếp theo

Ưu tiên xem lại hướng dẫn phân biệt OFFENSIVE/HATE và bổ sung ví dụ ngữ cảnh trên train/validation.
Khảo sát độ bền với không dấu, viết tắt và kéo dài ký tự bằng bộ đánh giá riêng; không sửa preprocessing
hiện tại rồi chọn phương án tốt nhất trên test này. Nếu cần triển khai, đo calibration và hành vi
abstain bằng validation/tập calibration; không dùng confidence softmax hiện có như xác suất đúng.
Mọi thay đổi sau khi đã xem test cần được công bố và đánh giá cuối trên holdout mới phù hợp.
