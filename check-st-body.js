const puppeteer = require('puppeteer');

(async () => {
    const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] });
    const page = await browser.newPage();
    
    page.on('response', async response => {
        if (!response.ok()) {
            try {
                const body = await response.text();
                console.log('FAILED REQUEST:', response.url(), response.status(), body.substring(0, 200));
            } catch (e) {
                console.log('FAILED REQUEST:', response.url(), response.status(), "(could not read body)");
            }
        }
    });

    try {
        await page.goto('https://bbvvbn-hshdbdbn.hf.space/', { waitUntil: 'networkidle0', timeout: 30000 });
        console.log("Page loaded successfully.");
    } catch (e) {
        console.log("Navigation error:", e.message);
    }

    await browser.close();
})();
