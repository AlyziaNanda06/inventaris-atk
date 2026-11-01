from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash
import pymysql
import os

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "local-dev-secret-change-me"
)


def get_db():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        cursorclass=pymysql.cursors.DictCursor,
        ssl_ca=os.path.join(
            os.path.dirname(__file__),
            "certs",
            "ca.pem"
        ),
        connect_timeout=10
    )


def query(sql, params=None, one=False):
    """Untuk SELECT: mengembalikan satu baris (one=True) atau banyak baris."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone() if one else cur.fetchall()
    finally:
        db.close()


def execute(sql, params=None):
    """Untuk INSERT / UPDATE / DELETE."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(sql, params or ())
        db.commit()
    finally:
        db.close()


@app.template_filter("rupiah")
def rupiah(nilai):
    try:
        return "Rp " + "{:,.0f}".format(float(nilai)).replace(",", ".")
    except (TypeError, ValueError):
        return nilai


@app.route("/")
def dashboard():
    ringkasan = query(
        """SELECT (SELECT COUNT(*) FROM barang) AS total_barang,
                  (SELECT COUNT(*) FROM supplier) AS total_supplier,
                  (SELECT COUNT(*) FROM kategori) AS total_kategori,
                  (SELECT COALESCE(SUM(stok * harga_beli), 0) FROM barang) AS nilai_persediaan""",
        one=True,
    )
    menipis = query(
        """SELECT kode_barang, nama_barang, stok, stok_minimum, satuan
           FROM barang WHERE stok <= stok_minimum ORDER BY stok"""
    )
    return render_template("dashboard.html", r=ringkasan, menipis=menipis)


@app.route("/kategori")
def kategori():
    data = query("SELECT * FROM kategori ORDER BY id_kategori")
    return render_template("kategori.html", data=data, edit=None)


@app.route("/kategori/edit/<int:id>")
def kategori_edit(id):
    data = query("SELECT * FROM kategori ORDER BY id_kategori")
    edit = query("SELECT * FROM kategori WHERE id_kategori=%s", (id,), one=True)
    return render_template("kategori.html", data=data, edit=edit)


@app.route("/kategori/simpan", methods=["POST"])
def kategori_simpan():
    id_k = request.form.get("id_kategori")
    nama = request.form["nama_kategori"].strip()
    ket = request.form["keterangan"].strip()
    if id_k:
        execute(
            "UPDATE kategori SET nama_kategori=%s, keterangan=%s WHERE id_kategori=%s",
            (nama, ket, id_k),
        )
        flash("Kategori berhasil diperbarui.", "success")
    else:
        execute("INSERT INTO kategori (nama_kategori, keterangan) VALUES (%s, %s)", (nama, ket))
        flash("Kategori berhasil ditambahkan.", "success")
    return redirect(url_for("kategori"))


@app.route("/kategori/hapus/<int:id>", methods=["POST"])
def kategori_hapus(id):
    try:
        execute("DELETE FROM kategori WHERE id_kategori=%s", (id,))
        flash("Kategori berhasil dihapus.", "success")
    except pymysql.err.IntegrityError:
        flash("Kategori tidak bisa dihapus karena masih dipakai oleh data barang.", "danger")
    return redirect(url_for("kategori"))


@app.route("/supplier")
def supplier():
    data = query("SELECT * FROM supplier ORDER BY id_supplier")
    return render_template("supplier.html", data=data, edit=None)


@app.route("/supplier/edit/<int:id>")
def supplier_edit(id):
    data = query("SELECT * FROM supplier ORDER BY id_supplier")
    edit = query("SELECT * FROM supplier WHERE id_supplier=%s", (id,), one=True)
    return render_template("supplier.html", data=data, edit=edit)


@app.route("/supplier/simpan", methods=["POST"])
def supplier_simpan():
    f = request.form
    nilai = (f["nama_supplier"].strip(), f["alamat"].strip(), f["telepon"].strip(), f["email"].strip())
    if f.get("id_supplier"):
        execute(
            """UPDATE supplier SET nama_supplier=%s, alamat=%s, telepon=%s, email=%s
               WHERE id_supplier=%s""",
            nilai + (f["id_supplier"],),
        )
        flash("Supplier berhasil diperbarui.", "success")
    else:
        execute(
            "INSERT INTO supplier (nama_supplier, alamat, telepon, email) VALUES (%s, %s, %s, %s)",
            nilai,
        )
        flash("Supplier berhasil ditambahkan.", "success")
    return redirect(url_for("supplier"))


@app.route("/supplier/hapus/<int:id>", methods=["POST"])
def supplier_hapus(id):
    try:
        execute("DELETE FROM supplier WHERE id_supplier=%s", (id,))
        flash("Supplier berhasil dihapus.", "success")
    except pymysql.err.IntegrityError:
        flash("Supplier tidak bisa dihapus karena sudah punya riwayat barang masuk.", "danger")
    return redirect(url_for("supplier"))


@app.route("/barang")
def barang():
    q = request.args.get("q", "").strip()
    sql = """SELECT b.*, k.nama_kategori
             FROM barang b JOIN kategori k ON b.id_kategori = k.id_kategori"""
    params = ()
    if q:
        sql += """ WHERE b.nama_barang LIKE %s OR b.kode_barang LIKE %s
                   OR k.nama_kategori LIKE %s"""
        params = (f"%{q}%",) * 3
    sql += " ORDER BY b.id_barang"
    return render_template("barang.html", data=query(sql, params), q=q)


@app.route("/barang/tambah", methods=["GET", "POST"])
@app.route("/barang/edit/<int:id>", methods=["GET", "POST"])
def barang_form(id=None):
    kategori_list = query("SELECT * FROM kategori ORDER BY nama_kategori")
    item = None
    if id:
        item = query("SELECT * FROM barang WHERE id_barang=%s", (id,), one=True)
        if item is None:
            flash("Barang tidak ditemukan.", "danger")
            return redirect(url_for("barang"))

    if request.method == "POST":
        f = request.form
        nilai = (
            f["kode_barang"].strip(), f["nama_barang"].strip(), f["id_kategori"],
            f["satuan"].strip(), f["harga_beli"], f["harga_jual"], f["stok_minimum"],
        )
        try:
            if id:
                execute(
                    """UPDATE barang SET kode_barang=%s, nama_barang=%s, id_kategori=%s,
                       satuan=%s, harga_beli=%s, harga_jual=%s, stok_minimum=%s
                       WHERE id_barang=%s""",
                    nilai + (id,),
                )
                flash("Data barang berhasil diperbarui.", "success")
            else:
                execute(
                    """INSERT INTO barang (kode_barang, nama_barang, id_kategori, satuan,
                       harga_beli, harga_jual, stok_minimum)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    nilai,
                )
                flash("Barang berhasil ditambahkan. Stok awal 0, isi lewat menu Barang Masuk.", "success")
            return redirect(url_for("barang"))
        except pymysql.err.IntegrityError:
            flash("Kode barang sudah dipakai, gunakan kode lain.", "danger")
            item = f   # supaya isian form tidak hilang

    judul = "Edit Barang" if id else "Tambah Barang"
    return render_template("barang_form.html", item=item, kategori_list=kategori_list, judul=judul)


@app.route("/barang/hapus/<int:id>", methods=["POST"])
def barang_hapus(id):
    try:
        execute("DELETE FROM barang WHERE id_barang=%s", (id,))
        flash("Barang berhasil dihapus.", "success")
    except pymysql.err.IntegrityError:
        flash("Barang tidak bisa dihapus karena sudah punya riwayat masuk/keluar.", "danger")
    return redirect(url_for("barang"))


@app.route("/masuk", methods=["GET", "POST"])
def masuk():
    if request.method == "POST":
        f = request.form
        jumlah = int(f["jumlah"])
        if jumlah <= 0:
            flash("Jumlah harus lebih dari 0.", "danger")
            return redirect(url_for("masuk"))

        db = get_db()
        try:
            with db.cursor() as cur:
                cur.execute(
                    """INSERT INTO barang_masuk
                       (id_barang, id_supplier, tanggal_masuk, jumlah, harga_beli)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (f["id_barang"], f["id_supplier"], f["tanggal_masuk"], jumlah, f["harga_beli"]),
                )
                cur.execute(
                    "UPDATE barang SET stok = stok + %s WHERE id_barang=%s",
                    (jumlah, f["id_barang"]),
                )
            db.commit()
            flash("Barang masuk berhasil dicatat, stok bertambah.", "success")
        except Exception:
            db.rollback()
            flash("Gagal menyimpan transaksi.", "danger")
        finally:
            db.close()
        return redirect(url_for("masuk"))

    data = query(
        """SELECT m.*, b.nama_barang, b.satuan, s.nama_supplier
           FROM barang_masuk m
           JOIN barang b ON m.id_barang = b.id_barang
           JOIN supplier s ON m.id_supplier = s.id_supplier
           ORDER BY m.tanggal_masuk DESC, m.id_masuk DESC"""
    )
    return render_template(
        "masuk.html", data=data, hari_ini=date.today().isoformat(),
        barang_list=query("SELECT * FROM barang ORDER BY nama_barang"),
        supplier_list=query("SELECT * FROM supplier ORDER BY nama_supplier"),
    )


@app.route("/keluar", methods=["GET", "POST"])
def keluar():
    if request.method == "POST":
        f = request.form
        jumlah = int(f["jumlah"])

        db = get_db()
        try:
            with db.cursor() as cur:
                cur.execute("SELECT stok FROM barang WHERE id_barang=%s FOR UPDATE", (f["id_barang"],))
                brg = cur.fetchone()
                if brg is None or jumlah <= 0:
                    flash("Data tidak valid.", "danger")
                elif brg["stok"] < jumlah:
                    flash(f"Stok tidak cukup. Stok tersedia: {brg['stok']}.", "danger")
                else:
                    cur.execute(
                        """INSERT INTO barang_keluar (id_barang, tanggal_keluar, jumlah, tujuan)
                           VALUES (%s, %s, %s, %s)""",
                        (f["id_barang"], f["tanggal_keluar"], jumlah, f["tujuan"].strip()),
                    )
                    cur.execute(
                        "UPDATE barang SET stok = stok - %s WHERE id_barang=%s",
                        (jumlah, f["id_barang"]),
                    )
                    db.commit()
                    flash("Barang keluar berhasil dicatat, stok berkurang.", "success")
        except Exception:
            db.rollback()
            flash("Gagal menyimpan transaksi.", "danger")
        finally:
            db.close()
        return redirect(url_for("keluar"))

    data = query(
        """SELECT kl.*, b.nama_barang, b.satuan
           FROM barang_keluar kl JOIN barang b ON kl.id_barang = b.id_barang
           ORDER BY kl.tanggal_keluar DESC, kl.id_keluar DESC"""
    )
    return render_template(
        "keluar.html", data=data, hari_ini=date.today().isoformat(),
        barang_list=query("SELECT * FROM barang ORDER BY nama_barang"),
    )


@app.route("/laporan/stok")
def laporan_stok():
    data = query(
        """SELECT b.kode_barang AS Kode, b.nama_barang AS Nama_Barang,
                  k.nama_kategori AS Kategori, b.stok AS Stok, b.satuan AS Satuan,
                  b.harga_beli AS Harga_Beli, (b.stok * b.harga_beli) AS Nilai_Persediaan,
                  CASE WHEN b.stok <= b.stok_minimum THEN 'MENIPIS' ELSE 'AMAN' END AS Status
           FROM barang b JOIN kategori k ON b.id_kategori = k.id_kategori
           ORDER BY k.nama_kategori, b.nama_barang"""
    )
    total = sum(r["Nilai_Persediaan"] for r in data)
    return render_template(
        "laporan.html", judul="Laporan Stok Barang", data=data,
        rupiah_cols=["Harga_Beli", "Nilai_Persediaan"],
        total_label="Total nilai persediaan", total=total,
        pakai_filter=False, dari="", sampai="",
    )


@app.route("/laporan/masuk")
def laporan_masuk():
    dari = request.args.get("dari", "")
    sampai = request.args.get("sampai", "")
    sql = """SELECT m.tanggal_masuk AS Tanggal, s.nama_supplier AS Supplier,
                    b.nama_barang AS Barang, m.jumlah AS Jumlah,
                    m.harga_beli AS Harga_Satuan, (m.jumlah * m.harga_beli) AS Total_Pembelian
             FROM barang_masuk m
             JOIN supplier s ON m.id_supplier = s.id_supplier
             JOIN barang b ON m.id_barang = b.id_barang
             WHERE 1=1"""
    params = []
    if dari:
        sql += " AND m.tanggal_masuk >= %s"
        params.append(dari)
    if sampai:
        sql += " AND m.tanggal_masuk <= %s"
        params.append(sampai)
    sql += " ORDER BY m.tanggal_masuk"
    data = query(sql, params)
    total = sum(r["Total_Pembelian"] for r in data)
    return render_template(
        "laporan.html", judul="Laporan Barang Masuk", data=data,
        rupiah_cols=["Harga_Satuan", "Total_Pembelian"],
        total_label="Total pembelian", total=total,
        pakai_filter=True, dari=dari, sampai=sampai,
    )


@app.route("/laporan/keluar")
def laporan_keluar():
    dari = request.args.get("dari", "")
    sampai = request.args.get("sampai", "")
    sql = """SELECT kl.tanggal_keluar AS Tanggal, b.nama_barang AS Barang,
                    kl.jumlah AS Jumlah, b.satuan AS Satuan, kl.tujuan AS Tujuan,
                    (kl.jumlah * b.harga_jual) AS Nilai_Keluar
             FROM barang_keluar kl JOIN barang b ON kl.id_barang = b.id_barang
             WHERE 1=1"""
    params = []
    if dari:
        sql += " AND kl.tanggal_keluar >= %s"
        params.append(dari)
    if sampai:
        sql += " AND kl.tanggal_keluar <= %s"
        params.append(sampai)
    sql += " ORDER BY kl.tanggal_keluar"
    data = query(sql, params)
    total = sum(r["Nilai_Keluar"] for r in data)
    return render_template(
        "laporan.html", judul="Laporan Barang Keluar", data=data,
        rupiah_cols=["Nilai_Keluar"],
        total_label="Total nilai barang keluar", total=total,
        pakai_filter=True, dari=dari, sampai=sampai,
    )


if __name__ == "__main__":
    app.run(debug=True)