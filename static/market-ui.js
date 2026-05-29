(function () {
    const storageKey = "campusMarketCart";
    const toast = document.querySelector("[data-toast]");
    const searchInput = document.querySelector("[data-search-input]");
    const searchForm = document.querySelector("[data-search-form]");
    const cartCount = document.querySelector("[data-cart-count]");
    const cartLists = [
        document.querySelector("[data-cart-list]"),
        document.querySelector("[data-cart-list-drawer]"),
    ].filter(Boolean);

    const readCart = () => {
        try {
            const items = JSON.parse(localStorage.getItem(storageKey) || "[]");
            const seen = new Set();
            const uniqueItems = items.filter((item) => {
                const key = item.id || item.name;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
            if (uniqueItems.length !== items.length) writeCart(uniqueItems);
            return uniqueItems;
        } catch (_) {
            return [];
        }
    };

    const writeCart = (items) => {
        localStorage.setItem(storageKey, JSON.stringify(items));
    };

    const showToast = (message) => {
        if (!toast) return;
        toast.textContent = message;
        toast.hidden = false;
        window.clearTimeout(showToast.timer);
        showToast.timer = window.setTimeout(() => {
            toast.hidden = true;
        }, 1800);
    };

    const renderCart = () => {
        const items = readCart();
        if (cartCount) cartCount.textContent = String(items.length);
        cartLists.forEach((list) => {
            list.innerHTML = "";
            if (!items.length) {
                const empty = document.createElement("div");
                empty.className = "cart-item";
                empty.textContent = "還沒有加入商品。";
                list.append(empty);
                return;
            }
            items.forEach((item) => {
                const row = document.createElement("div");
                row.className = "cart-item";
                const label = document.createElement("span");
                label.textContent = `${item.name} · NT$ ${item.price}`;
                const remove = document.createElement("button");
                remove.className = "remove-cart-button";
                remove.type = "button";
                remove.dataset.removeCart = item.id || item.name;
                remove.textContent = "移除";
                row.append(label, remove);
                list.append(row);
            });
        });
    };

    const openDrawer = (name) => {
        document.querySelectorAll("[data-drawer]").forEach((drawer) => {
            drawer.hidden = drawer.dataset.drawer !== name;
        });
    };

    document.querySelectorAll("[data-open-drawer]").forEach((button) => {
        button.addEventListener("click", () => openDrawer(button.dataset.openDrawer));
    });

    document.querySelectorAll("[data-close-drawer]").forEach((button) => {
        button.addEventListener("click", () => {
            const drawer = button.closest("[data-drawer]");
            if (drawer) drawer.hidden = true;
        });
    });

    cartLists.forEach((list) => {
        list.addEventListener("click", (event) => {
            const button = event.target.closest("[data-remove-cart]");
            if (!button) return;
            const key = button.dataset.removeCart;
            const items = readCart().filter((item) => (item.id || item.name) !== key);
            writeCart(items);
            renderCart();
            showToast("已從待看清單移除。");
        });
    });

    document.querySelectorAll("[data-focus-search]").forEach((button) => {
        button.addEventListener("click", () => {
            searchInput?.focus();
            showToast("搜尋列已準備好。");
        });
    });

    document.querySelectorAll("[data-search-chip]").forEach((chip) => {
        chip.addEventListener("click", () => {
            if (!searchInput) return;
            searchInput.value = chip.dataset.searchChip || "";
            searchInput.focus();
            showToast(`已填入「${searchInput.value}」`);
        });
    });

    document.querySelectorAll("[data-add-cart]").forEach((button) => {
        button.addEventListener("click", () => {
            const card = button.closest("[data-product-card]");
            if (!card) return;
            const items = readCart();
            const id = card.dataset.productId;
            const name = card.dataset.productName;
            if (items.some((item) => item.id === id || item.name === name)) {
                showToast("這個商品已經在待看清單了。");
                return;
            }
            items.push({
                id,
                name,
                price: card.dataset.productPrice,
            });
            writeCart(items);
            renderCart();
            showToast("已加入待看清單。");
        });
    });

    document.querySelectorAll("[data-save-item]").forEach((button) => {
        button.addEventListener("click", () => {
            const active = button.classList.toggle("active");
            button.textContent = active ? "★" : "☆";
            showToast(active ? "已收藏商品。" : "已取消收藏。");
        });
    });

    document.querySelectorAll("[data-card-filter]").forEach((button) => {
        button.addEventListener("click", () => {
            document.querySelectorAll("[data-card-filter]").forEach((item) => item.classList.remove("active"));
            button.classList.add("active");

            const filter = button.dataset.cardFilter;
            document.querySelectorAll("[data-product-card]").forEach((card, index) => {
                const tags = (card.dataset.productTags || "").toLowerCase();
                const price = Number(card.dataset.productPrice || 0);
                let show = true;
                if (filter === "new") show = tags.includes("新") || tags.includes("九成");
                if (filter === "used") show = tags.includes("二手") || tags.includes("良品") || index % 2 === 0;
                if (filter === "sale") show = tags.includes("急售") || tags.includes("可議價") || price <= 300;
                card.hidden = !show;
            });
        });
    });

    searchForm?.addEventListener("submit", () => {
        showToast("正在幫你搜尋校園好物。");
    });

    renderCart();
})();
