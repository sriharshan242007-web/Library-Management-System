const $ = id => document.getElementById(id);
let selectedBook = null;

function getBookById(id) {
    if (typeof INITIAL_BOOKS !== 'undefined' && Array.isArray(INITIAL_BOOKS)) {
        return INITIAL_BOOKS.find(b => b.book_id === id);
    }
    return null;
}

function openBorrowById(bookId) {
    const book = getBookById(bookId);
    if (!book) return;
    selectedBook = book;
    
    $('bookId').value = book.book_id;
    $('modalTitle').textContent = book.title;
    $('modalAuthor').textContent = book.author;
    $('modalAvail').textContent = `${book.available_copies} available`;
    
    // Extract integer from book_id (e.g., 'B001' -> 1)
    const numericPart = parseInt(book.book_id.replace(/\D/g, ''), 10) || 1;
    const coverNum = ((numericPart - 1) % 8) + 1;
    $('modalCover').className = `modalcover c${coverNum}`;
    
    $('formError').textContent = '';
    $('borrowModal').classList.add('show');
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    const modal = $('borrowModal');
    if (modal) modal.classList.remove('show');
    document.body.style.overflow = '';
}

function closeSuccess() {
    const successModal = $('successModal');
    if (successModal) successModal.classList.remove('show');
    document.body.style.overflow = '';
    location.reload();
}

document.addEventListener('DOMContentLoaded', () => {
    const borrowForm = $('borrowForm');
    if (borrowForm) {
        borrowForm.addEventListener('submit', async e => {
            e.preventDefault();
            $('formError').textContent = '';
            
            const data = {
                book_id: $('bookId').value,
                name: $('name').value,
                student_id: $('studentId').value,
                email: $('email').value,
                phone: $('phone').value,
                department: $('department').value
            };

            try {
                const r = await fetch('/api/borrow', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                
                const out = await r.json();
                if (!r.ok || !out.success) {
                    $('formError').textContent = out.message || 'Unable to complete borrowing.';
                    return;
                }

                borrowForm.reset();
                closeModal();

                $('successMessage').textContent = `"${out.book}" has been issued successfully. Your borrowing record is now saved in the library database.`;
                $('issueId').textContent = out.issue_id;
                $('dueDate').textContent = out.due_date;
                $('successModal').classList.add('show');
                document.body.style.overflow = 'hidden';
            } catch (err) {
                $('formError').textContent = 'Server connection failed. Make sure Flask is running.';
            }
        });
    }

    const searchInput = $('search');
    const categorySelect = $('category');
    const grid = $('grid');
    const emptyState = $('empty');

    function filterCatalog() {
        if (!grid) return;
        const q = searchInput ? searchInput.value.toLowerCase().trim() : '';
        const cat = categorySelect ? categorySelect.value : '';
        let visibleCount = 0;

        grid.querySelectorAll('.card').forEach(card => {
            const title = card.dataset.title || '';
            const author = card.dataset.author || '';
            const category = card.dataset.category || '';

            const matchesQuery = !q || title.includes(q) || author.includes(q);
            const matchesCategory = !cat || category === cat;

            const isMatch = matchesQuery && matchesCategory;
            card.style.display = isMatch ? '' : 'none';
            if (isMatch) visibleCount++;
        });

        if (emptyState) {
            emptyState.hidden = visibleCount !== 0;
        }
    }

    if (searchInput) searchInput.addEventListener('input', filterCatalog);
    if (categorySelect) categorySelect.addEventListener('change', filterCatalog);

    document.querySelectorAll('.overlay').forEach(overlay => {
        overlay.addEventListener('click', e => {
            if (e.target === overlay) {
                overlay.classList.remove('show');
                document.body.style.overflow = '';
            }
        });
    });
});