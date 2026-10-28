# راهنمای فارسی پروژه: سیستم مدیریت کتابخانه

## ۱. این تکلیف چه چیزی می‌خواهد؟

باید یک **برنامه خط فرمان (CLI)** با **پایتون + SQLAlchemy 2.0** بسازی که یک کتابخانه کوچک را مدیریت کند. خلاصه خواسته‌ها و جای انجام هرکدام:

| خواسته | جای انجام در پروژه |
|--------|-----------------|
| حداقل ۳ جدول: `books`، `authors`، `members` | `models.py` ✅ |
| رابطه چند‌به‌چند کتاب ↔ نویسنده با جدول واسط | جدول `book_authors` در `models.py` ✅ |
| رابطه کتاب ↔ عضو (امانت) با `checkout_date` و `return_date` | مدل `Borrowing` در `models.py` ✅ |
| مدل‌ها با `Mapped` و `mapped_column()`، بدون `CREATE TABLE` دستی | `models.py` ✅ |
| CRUD: افزودن کتاب/عضو/نویسنده، امانت دادن، جستجو، لیست امانت‌ها، دیرکردها، برگرداندن، تغییر ایمیل، حذف کتاب و عضو با شرط | `crud.py` ✅ |
| منوی خط فرمان که تا Exit تکرار شود | `main.py` ✅ |
| تابع داده نمونه (حداقل ۵ کتاب، ۳ نویسنده، ۴ عضو، ۶ امانت که بعضی برگشته‌اند) | `seed.py` و `sample_data.json` ✅ (۷ کتاب، ۴ نویسنده، ۵ عضو، ۸ امانت) |
| کدِ جدا شده در چند فایل، docstring برای توابع | ✅ |
| README با ERD، راه‌اندازی و نحوه استفاده | `README.md` ✅ |
| مدرک تست شدن | پوشه `tests/` (۳۶ تست، همه پاس) و پوشه `docs/` ✅ |
| **ارائه ۵ دقیقه‌ای** | **این بخش با خودت است.** متن آماده در بخش ۴ پایین‌تر هست. |

## ۲. اجرای پروژه روی مک

ترمینال را باز کن و در پوشه پروژه این دستورها را بزن:

```bash
cd library-management-system
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python seed.py        # پاک کردن دیتابیس و پر کردن با داده نمونه
python main.py        # اجرای برنامه
python -m pytest -v   # اجرای تست‌ها (باید بنویسد 36 passed)
```

## ۳. کار نهایی تو (به ترتیب)

1. **کد را بفهم.** برای ارائه باید بتوانی توضیحش بدهی. اول `models.py` را بخوان، بعد `crud.py`. کامنت‌ها و docstringها همه‌چیز را توضیح می‌دهند.
2. **روی کامپیوتر خودت اجرا کن** (بخش ۲) و همه گزینه‌های منو را یک بار امتحان کن.
3. **یک ریپوی جدید در GitHub بساز**، مثلاً با نام `library-management-system`، و محتویات این پوشه را در آن آپلود کن (`git add`، `git commit`، `git push`). فایل `library.db` و پوشه `venv` به خاطر `.gitignore` آپلود نمی‌شوند و نباید هم بشوند.
4. **ارسال:** در بخش Submit Project سایت Coding Temple، لینک ریپوی GitHub را در قسمت Link بگذار. در Submission Body هم یک توضیح کوتاه بنویس (متن آماده در بخش ۵).
5. **ارائه ۵ دقیقه‌ای را تمرین کن** (بخش ۴). قبل از ارائه حتماً `python seed.py` را بزن تا داده‌ها تمیز باشند.
6. اگر شرایط درس اجازه می‌دهد، ERD را در draw.io هم بکش. نمودار Mermaid داخل README در GitHub خودکار به شکل تصویر نمایش داده می‌شود و کافی است.

> نکته: داده‌های نمونه با «چند روز قبل» ذخیره شده‌اند، پس هر روز که `seed.py` را بزنی، دو کتاب دیرکرد خواهند داشت.

## ۴. متن آماده ارائه ۵ دقیقه‌ای (به انگلیسی)

**ERD (۱ دقیقه).** README را در GitHub باز کن و نمودار را نشان بده:
> "I have five tables. `books`, `authors` and `members` are the main ones. Books and authors are **many-to-many**, because a book can have several authors, like *Good Omens*, and an author writes many books. I used an association table called `book_authors`. Books and members are connected through `borrowings`. It has foreign keys to both tables plus `checkout_date` and `return_date`. If `return_date` is NULL, the book is still out. So book-to-borrowings and member-to-borrowings are both **one-to-many**."

**دموی زنده (۲.۵ دقیقه).** `python main.py` را اجرا کن:
1. گزینه `1` را بزن و یک کتاب اضافه کن (مثلاً Dune، `978-0-441-17271-9`، 1965، تعداد 1 نسخه، Frank Herbert).
2. گزینه `4` را بزن و آن را به Emma امانت بده (عضو 5). نشان بده موجودی صفر شد.
3. *(اختیاری)* دوباره `4` را بزن و همان کتاب را برای Alice امتحان کن. پیغام خطای «no available copies» نشان داده می‌شود.
4. گزینه `6` را بزن و امانت‌های Emma را ببین.
5. گزینه `5` را بزن و کتاب را برگردان. موجودی دوباره 1 می‌شود.
6. *(اختیاری)* گزینه `7` لیست دیرکردها را نشان می‌دهد.

**تصمیم طراحی (۱ دقیقه):**
> "I made Borrowing its own model instead of a plain association table, because it has its own data and the same member can borrow the same book more than once. When someone checks out a book, I create the borrowing and lower `available_copies` in **one transaction**. If anything fails, everything is rolled back, so the copy count can never get out of sync. There's also a CHECK constraint so copies can't go negative."

**سخت‌ترین بخش (۳۰ ثانیه):**
> "The hardest part was data integrity, for example making sure a book can't be returned twice, which would add a copy twice. I solved it by keeping all business rules in `crud.py` and wrapping every change in a transaction that rolls back on error. I also found out that SQLite ignores foreign keys by default, so I had to turn them on with `PRAGMA foreign_keys=ON`."

## ۵. متن پیشنهادی برای Submission Body

```
Library Management System: Python CLI with SQLAlchemy 2.0 and SQLite.
- 5 tables: books, authors, members, book_authors (many-to-many), borrowings (books <-> members with checkout/return dates)
- Full CRUD with business rules (no borrowing unavailable books, no deleting books that are checked out or members with active borrowings)
- Overdue detection (14-day loan), input validation, rollback on errors
- Seed script with sample data; 36 automated tests (pytest), all passing
- README includes ERD, setup and usage instructions
```

## ۶. سؤال‌های احتمالی استاد

- **چرا `bio` می‌تواند خالی باشد؟** چون در صورت تکلیف اختیاری است: `Mapped[Optional[str]]` با `nullable=True`.
- **دیرکرد چطور حساب می‌شود؟** امانتی که برنگشته (`return_date IS NULL`) و بیشتر از ۱۴ روز از `checkout_date` آن گذشته باشد. به تابع `list_overdue_books` نگاه کن.
- **اگر کتابی که برگشته را حذف کنیم، تاریخچه‌اش چه می‌شود؟** با `cascade="all, delete-orphan"` همراه کتاب حذف می‌شود. کتابی که هنوز امانت است اصلاً حذف نمی‌شود.
- **rollback کجاست؟** تابع `_transaction` در `crud.py` (یک context manager که در صورت خطا `session.rollback()` می‌زند).
