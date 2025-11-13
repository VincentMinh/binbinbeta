# employees.py
# File quản lý danh sách nhân viên - Nguồn dữ liệu gốc (Single Source of Truth)
# Đã cập nhật theo kiến trúc mới với employee_id, code, và shift.

employees = [
#--------------------------------------- BIN BIN HOTEL 1 --------------------------------------------#
    {
        "employee_id": "NV001", "code": "B1LT01", "name": "Phạm Thị Quỳnh Như",
        "role": "letan", "branch": "B1", "shift": "CS"
    },
    {
        "employee_id": "NV002", "code": "B1LT02", "name": "Trần Thị Mỹ Diễm",
        "role": "letan", "branch": "B1", "shift": "CT"
    },
    {
        "employee_id": "NV003", "code": "B1BP01", "name": "Đỗ Kim Phượng",
        "role": "buongphong", "branch": "B1", "shift": "CS"
    },
#--------------------------------------- BIN BIN HOTEL 2 --------------------------------------------#
    {
        "employee_id": "NV004", "code": "B2LT01", "name": "Phan Phương Thúy",
        "role": "letan", "branch": "B2", "shift": "CS"
    },
    {
        "employee_id": "NV005", "code": "B2LT02", "name": "Ngô Bảo Trân",
        "role": "letan", "branch": "B2", "shift": "CT"
    },
    {
        "employee_id": "NV006", "code": "B2BP01", "name": "Nguyễn Thị Ngọc Linh",
        "role": "buongphong", "branch": "B2", "shift": "CS"
    },
    {
        "employee_id": "NV007", "code": "B2BP02", "name": "Cao Đức Thẫm",
        "role": "buongphong", "branch": "B2", "shift": "CT"
    },
#--------------------------------------- BIN BIN HOTEL 3 --------------------------------------------#
    {
        "employee_id": "NV008", "code": "B3LT01", "name": "Võ Thị Ngọc Trân",
        "role": "letan", "branch": "B3", "shift": "CS"
    },
    {
        "employee_id": "NV009", "code": "B3LT02", "name": "Trần Nguyễn Gia Ân",
        "role": "letan", "branch": "B3", "shift": "CT"
    },
    {
        "employee_id": "NV010", "code": "B3BP01", "name": "Trần Mỹ Châu",
        "role": "buongphong", "branch": "B3", "shift": "CS"
    },
#--------------------------------------- BIN BIN HOTEL 5 --------------------------------------------#
    {
        "employee_id": "NV011", "code": "B5LT01", "name": "Nguyễn Thị Cẩm Tú",
        "role": "letan", "branch": "B5", "shift": "CS"
    },
    {
        "employee_id": "NV012", "code": "B5LT02", "name": "Huỳnh Nguyễn Hoàng Dung",
        "role": "letan", "branch": "B5", "shift": "CT"
    },
    {
        "employee_id": "NV013", "code": "B5BP01", "name": "Đặng Thị Kim Mai",
        "role": "buongphong", "branch": "B5", "shift": "CS"
    },
    {
        "employee_id": "NV014", "code": "B5BP02", "name": "Nguyễn Thị Điệp",
        "role": "buongphong", "branch": "B5", "shift": "CT"
    },
#--------------------------------------- BIN BIN HOTEL 6 --------------------------------------------#
    {
        "employee_id": "NV015", "code": "B6LT01", "name": "Nguyễn Thị Mai Huỳnh",
        "role": "letan", "branch": "B6", "shift": "CS"
    },
    {
        "employee_id": "NV016", "code": "B6LT02", "name": "Nguyễn Đăng Khải",
        "role": "letan", "branch": "B6", "shift": "CT"
    },
    {
        "employee_id": "NV017", "code": "B6BP01", "name": "Nguyễn Thị Kim Xuyến",
        "role": "buongphong", "branch": "B6", "shift": "CS"
    },
#--------------------------------------- BIN BIN HOTEL 7 --------------------------------------------#
    {
        "employee_id": "NV018", "code": "B7LT01", "name": "Nguyễn Thị Băng Huyền",
        "role": "letan", "branch": "B7", "shift": "CS"
    },
    {
        "employee_id": "NV019", "code": "B7LT02", "name": "Phạm Thành Trí",
        "role": "letan", "branch": "B7", "shift": "CT"
    },
    {
        "employee_id": "NV020", "code": "B7BP01", "name": "Thạch Thị Bô Na",
        "role": "buongphong", "branch": "B7", "shift": "CS"
    },
    {
        "employee_id": "NV021", "code": "B7BP02", "name": "Trần Thị Tuyết Nga",
        "role": "buongphong", "branch": "B7", "shift": "CS"
    },
    {
        "employee_id": "NV022", "code": "B7BP03", "name": "Trần Thị Yến",
        "role": "buongphong", "branch": "B7", "shift": "CT"
    },
#--------------------------------------- BIN BIN HOTEL 8 --------------------------------------------#
    {
        "employee_id": "NV023", "code": "B8LT01", "name": "Tô Phương Mai",
        "role": "letan", "branch": "B8", "shift": "CS"
    },
    {
        "employee_id": "NV024", "code": "B8LT02", "name": "Nguyễn Văn Hoàng",
        "role": "letan", "branch": "B8", "shift": "CT"
    },
    {
        "employee_id": "NV025", "code": "B8BP01", "name": "Nguyễn Thị Nhi",
        "role": "buongphong", "branch": "B8", "shift": "CS"
    },
    {
        "employee_id": "NV026", "code": "B8BP02", "name": "Huỳnh Thị Kim Ngân",
        "role": "buongphong", "branch": "B8", "shift": "CS"
    },
    {
        "employee_id": "NV027", "code": "B8BP03", "name": "Trương Thị Thanh Hải",
        "role": "buongphong", "branch": "B8", "shift": "CT"
    },
#--------------------------------------- BIN BIN HOTEL 9 --------------------------------------------#
    {
        "employee_id": "NV028", "code": "B9LT01", "name": "Đặng Thụy Yến Nhi",
        "role": "letan", "branch": "B9", "shift": "CS"
    },
    {
        "employee_id": "NV029", "code": "B9LT02", "name": "Lê Quang Hoàng An",
        "role": "letan", "branch": "B9", "shift": "CT"
    },
    {
        "employee_id": "NV030", "code": "B9BP01", "name": "Phan Bảo Trân",
        "role": "buongphong", "branch": "B9", "shift": "CS"
    },
    {
        "employee_id": "NV031", "code": "B9BP02", "name": "Đinh Kim Thanh",
        "role": "buongphong", "branch": "B9", "shift": "CT"
    },
#--------------------------------------- BIN BIN HOTEL 10 --------------------------------------------#
    {
        "employee_id": "NV032", "code": "B10LT01", "name": "Lê Thị Thanh Trinh",
        "role": "letan", "branch": "B10", "shift": "CS"
    },
    {
        "employee_id": "NV033", "code": "B10LT02", "name": "Nguyễn Ngọc Tuấn",
        "role": "letan", "branch": "B10", "shift": "CT"
    },
    {
        "employee_id": "NV034", "code": "B10BP01", "name": "Nguyễn Thị Tuyết",
        "role": "buongphong", "branch": "B10", "shift": "CS"
    },
    {
        "employee_id": "NV035", "code": "B10BP02", "name": "Lê Thị Kim Dung",
        "role": "buongphong", "branch": "B10", "shift": "CT"
    },
#--------------------------------------- BIN BIN HOTEL 11 --------------------------------------------#
    {
        "employee_id": "NV036", "code": "B11LT01", "name": "Bùi Thị Thanh Trúc",
        "role": "letan", "branch": "B11", "shift": "CS"
    },
    {
        "employee_id": "NV037", "code": "B11LT02", "name": "Khổng Quang Chung",
        "role": "letan", "branch": "B11", "shift": "CT"
    },
    {
        "employee_id": "NV038", "code": "B11BP01", "name": "Phạm Thị Hằng",
        "role": "buongphong", "branch": "B11", "shift": "CS"
    },
    {
        "employee_id": "NV039", "code": "B11BP02", "name": "Lê Thị Hồng Yến",
        "role": "buongphong", "branch": "B11", "shift": "CS"
    },
    {
        "employee_id": "NV040", "code": "B11BP03", "name": "Phạm Tố Uyên",
        "role": "buongphong", "branch": "B11", "shift": "CT"
    },
    {
        "employee_id": "NV041", "code": "B11BV01", "name": "Tạ Văn Hoàng",
        "role": "baove", "branch": "B11", "shift": "CS"
    },
    {
        "employee_id": "NV042", "code": "B11BV02", "name": "Võ Quốc Thái",
        "role": "baove", "branch": "B11", "shift": "CT"
    },
#--------------------------------------- BIN BIN HOTEL 12 --------------------------------------------#
    {
        "employee_id": "NV043", "code": "B12LT01", "name": "Tô Thảo Trang",
        "role": "letan", "branch": "B12", "shift": "CS"
    },
    {
        "employee_id": "NV044", "code": "B12LT02", "name": "Lâm Hồng Phúc",
        "role": "letan", "branch": "B12", "shift": "CT"
    },
    {
        "employee_id": "NV045", "code": "B12BP01", "name": "Nguyễn Thị Ánh Tuyết",
        "role": "buongphong", "branch": "B12", "shift": "CS"
    },
    {
        "employee_id": "NV046", "code": "B12BP02", "name": "Nguyễn Thị Chinh",
        "role": "buongphong", "branch": "B12", "shift": "CT"
    },
#--------------------------------------- BIN BIN HOTEL 14 --------------------------------------------#
    {
        "employee_id": "NV047", "code": "B14LT01", "name": "Nguyễn Thị Khánh Vy",
        "role": "letan", "branch": "B14", "shift": "CS"
    },
    {
        "employee_id": "NV048", "code": "B14LT02", "name": "Ngô Thanh Trang",
        "role": "letan", "branch": "B14", "shift": "CT"
    },
    {
        "employee_id": "NV049", "code": "B14BP01", "name": "Thị Duyên",
        "role": "buongphong", "branch": "B14", "shift": "CS"
    },
    {
        "employee_id": "NV050", "code": "B14BP02", "name": "Trần Thanh Giàu",
        "role": "buongphong", "branch": "B14", "shift": "CT"
    },
#--------------------------------------- BIN BIN HOTEL 15 --------------------------------------------#
    {
        "employee_id": "NV051", "code": "B15LT01", "name": "Lê Thị Yến Oanh",
        "role": "letan", "branch": "B15", "shift": "CS"
    },
    {
        "employee_id": "NV052", "code": "B15LT02", "name": "Lê Trường Giang",
        "role": "letan", "branch": "B15", "shift": "CT"
    },
    {
        "employee_id": "NV053", "code": "B15BP01", "name": "Nguyễn Thị Mỹ Trúc",
        "role": "buongphong", "branch": "B15", "shift": "CS"
    },
    {
        "employee_id": "NV054", "code": "B15BP02", "name": "Nguyễn Thành Vũ",
        "role": "buongphong", "branch": "B15", "shift": "CS"
    },
    {
        "employee_id": "NV055", "code": "B15BP03", "name": "Trần Thị Thanh Nhãn",
        "role": "buongphong", "branch": "B15", "shift": "CT"
    },
    {
        "employee_id": "NV056", "code": "B15BV01", "name": "Bùi Minh Nghĩa",
        "role": "baove", "branch": "B15", "shift": "CT"
    },
#--------------------------------------- BIN BIN HOTEL 16 --------------------------------------------#
    {
        "employee_id": "NV057", "code": "B16LT01", "name": "Nguyễn Hoàng Thanh Minh",
        "role": "letan", "branch": "B16", "shift": "CS"
    },
    {
        "employee_id": "NV058", "code": "B16LT02", "name": "Lê Hữu Nghĩa",
        "role": "letan", "branch": "B16", "shift": "CT"
    },
    {
        "employee_id": "NV059", "code": "B16BP01", "name": "Trần Thanh Phú",
        "role": "buongphong", "branch": "B16", "shift": "CT"
    },
    {
        "employee_id": "NV060", "code": "B16BP02", "name": "Lê Thị Tám",
        "role": "buongphong", "branch": "B16", "shift": "CS"
    },
#--------------------------------------- LỄ TÂN CHẠY CA --------------------------------------------#
    # Các vai trò đặc biệt, không thuộc chi nhánh cố định
    {
        "employee_id": "NV061", "code": "LTTC01", "name": "Lê Minh Trung",
        "role": "letan", "branch": "DI DONG", "shift": None # Ca làm việc linh hoạt
    },
    {
        "employee_id": "NV062", "code": "LTTC02", "name": "Nguyễn Đỗ Minh Luân",
        "role": "letan", "branch": "DI DONG", "shift": None
    },
    {
        "employee_id": "NV063", "code": "LTTC03", "name": "Trần Thiện Tín",
        "role": "letan", "branch": "DI DONG", "shift": None
    },
#--------------------------------------- BUỒNG PHÒNG CHẠY CA --------------------------------------------#
    {
        "employee_id": "NV064", "code": "BPTC01", "name": "Lê Trọng Phúc",
        "role": "buongphong", "branch": "DI DONG", "shift": None
    },
    {
        "employee_id": "NV065", "code": "BPTC02", "name": "Trần Ngọc Ánh",
        "role": "buongphong", "branch": "DI DONG", "shift": None
    },
    {
        "employee_id": "NV066", "code": "BPTC03", "name": "Võ Thị Diệu Lý",
        "role": "buongphong", "branch": "DI DONG", "shift": None
    },
#--------------------------------------- QUẢN LÍ VÀ KTV --------------------------------------------#
    {
        "employee_id": "NV067", "code": "KTV", "name": "Lê Trọng Phúc",
        "role": "ktv", "branch": "KTV", "shift": None # Không quản lý ca
    },
    {
        "employee_id": "NV068", "code": "QL01", "name": "Trần Phát Nguyên",
        "role": "quanly", "branch": "QL", "shift": None
    },
    {
        "employee_id": "NV069", "code": "QL02", "name": "Trần Ngọc Ánh",
        "role": "quanly", "branch": "QL", "shift": None
    },
    {
        "employee_id": "NV070", "code": "QL03", "name": "Nguyễn Đỗ Minh Luân",
        "role": "quanly", "branch": "QL", "shift": None
    },
    {
        "employee_id": "NV071", "code": "QL04", "name": "Mr. Thuật",
        "role": "quanly", "branch": "QL", "shift": None
    },
#--------------------------------------- ADMIN & BAN GIÁM ĐỐC --------------------------------------------#
    {
        "employee_id": "NV997", "code": "Admin", "name": "Vincent Minh",
        "role": "admin", "branch": "ADMIN", "shift": None
    },
    {
        "employee_id": "NV998", "code": "ThuyLinh", "name": "Thùy Linh",
        "role": "admin", "branch": "ADMIN", "shift": None
    },
    {
        "employee_id": "NV999", "code": "Boss", "name": "Sếp Bin",
        "role": "boss", "branch": "BOSS", "shift": None
    },
]