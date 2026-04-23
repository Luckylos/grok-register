#!/usr/bin/env python3
"""注册流程 — 打开页面/填邮箱/填验证码/填资料/Turnstile/提交"""

import secrets
import time
import random

from DrissionPage.errors import PageDisconnectedError

import browser
from browser import refresh_active_page, restart_browser
from email_register import get_email_and_token, get_oai_code
from logger import logger, run_logger

SIGNUP_URL = "https://accounts.x.ai/sign-up?redirect=grok-com"


def open_signup_page():
	refresh_active_page()
	try:
		browser.page.get(SIGNUP_URL)
	except Exception:
		refresh_active_page()
		browser.page = browser.browser.new_tab(SIGNUP_URL)
	click_email_signup_button()


def click_email_signup_button(timeout=10):
	deadline = time.time() + timeout
	while time.time() < deadline:
		clicked = browser.page.run_js(r"""
const candidates = Array.from(document.querySelectorAll('button, a, [role="button"]'));
const target = candidates.find((node) => {
	const text = (node.innerText || node.textContent || '').replace(/\s+/g, '').toLowerCase();
	return text.includes('使用邮箱注册') || text.includes('signupwithemail') || text.includes('signupemail') || text.includes('continuewith email') || text.includes('email');
});

if (!target) {
	return false;
}

target.click();
return true;
		""")

		if clicked:
			return True

		time.sleep(0.5)

	raise Exception('未找到"使用邮箱注册"按钮')


def fill_email_and_submit(timeout=15):
	email, dev_token = get_email_and_token()
	if not email or not dev_token:
		raise Exception("获取邮箱失败")

	deadline = time.time() + timeout
	while time.time() < deadline:
		filled = browser.page.run_js(
			"""
const email = arguments[0];

function isVisible(node) {
	if (!node) {
		return false;
	}
	const style = window.getComputedStyle(node);
	if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
		return false;
	}
	const rect = node.getBoundingClientRect();
	return rect.width > 0 && rect.height > 0;
}

const input = Array.from(document.querySelectorAll('input[data-testid="email"], input[name="email"], input[type="email"], input[autocomplete="email"]')).find((node) => {
	return isVisible(node) && !node.disabled && !node.readOnly;
}) || null;

if (!input) {
	return 'not-ready';
}

input.focus();
input.click();

const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
const tracker = input._valueTracker;
if (tracker) {
	tracker.setValue('');
}
if (valueSetter) {
	valueSetter.call(input, email);
} else {
	input.value = email;
}

input.dispatchEvent(new InputEvent('beforeinput', {
	bubbles: true,
	data: email,
	inputType: 'insertText',
}));
input.dispatchEvent(new InputEvent('input', {
	bubbles: true,
	data: email,
	inputType: 'insertText',
}));
input.dispatchEvent(new Event('change', { bubbles: true }));

if ((input.value || '').trim() !== email || !input.checkValidity()) {
	return false;
}

input.blur();
return 'filled';
			""",
			email,
		)

		if filled == 'not-ready':
			time.sleep(0.5)
			continue

		if filled != 'filled':
			logger.warning(f"邮箱输入框已出现，但写入失败: {filled}")
			time.sleep(0.5)
			continue

		if filled == 'filled':
			time.sleep(0.8)
			clicked = browser.page.run_js(
				r"""
function isVisible(node) {
	if (!node) {
		return false;
	}
	const style = window.getComputedStyle(node);
	if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
		return false;
	}
	const rect = node.getBoundingClientRect();
	return rect.width > 0 && rect.height > 0;
}

const input = Array.from(document.querySelectorAll('input[data-testid="email"], input[name="email"], input[type="email"], input[autocomplete="email"]')).find((node) => {
	return isVisible(node) && !node.disabled && !node.readOnly;
}) || null;

if (!input || !input.checkValidity() || !(input.value || '').trim()) {
	return false;
}

const buttons = Array.from(document.querySelectorAll('button[type="submit"], button')).filter((node) => {
	return isVisible(node) && !node.disabled && node.getAttribute('aria-disabled') !== 'true';
});
const submitButton = buttons.find((node) => {
	const text = (node.innerText || node.textContent || '').replace(/\s+/g, '');
	const t = text.toLowerCase(); return text === '注册' || text.includes('注册') || t === 'signup' || t === 'sign up' || t.includes('sign up');
});

if (!submitButton || submitButton.disabled) {
	return false;
}

submitButton.click();
return true;
				"""
			)

			if clicked:
				logger.info(f"已填写邮箱并点击注册: {email}")
				return email, dev_token

		time.sleep(0.5)

	raise Exception("未找到邮箱输入框或注册按钮")


def fill_code_and_submit(email, dev_token, timeout=60):
	code = get_oai_code(dev_token, email)
	if not code:
		raise Exception("获取验证码失败")

	deadline = time.time() + timeout
	while time.time() < deadline:
		try:
			filled = browser.page.run_js(
				"""
const code = String(arguments[0] || '').trim();

function isVisible(node) {
	if (!node) {
		return false;
	}
	const style = window.getComputedStyle(node);
	if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
		return false;
	}
	const rect = node.getBoundingClientRect();
	return rect.width > 0 && rect.height > 0;
}

function setNativeValue(input, value) {
	const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
	const tracker = input._valueTracker;
	if (tracker) {
		tracker.setValue('');
	}
	if (nativeInputValueSetter) {
		nativeInputValueSetter.call(input, '');
		nativeInputValueSetter.call(input, value);
	} else {
		input.value = '';
		input.value = value;
	}
}

function dispatchInputEvents(input, value) {
	input.dispatchEvent(new InputEvent('beforeinput', {
		bubbles: true,
		cancelable: true,
		data: value,
		inputType: 'insertText',
	}));
	input.dispatchEvent(new InputEvent('input', {
		bubbles: true,
		cancelable: true,
		data: value,
		inputType: 'insertText',
	}));
	input.dispatchEvent(new Event('change', { bubbles: true }));
}

const input = Array.from(document.querySelectorAll('input[data-input-otp="true"], input[name="code"], input[autocomplete="one-time-code"], input[inputmode="numeric"], input[inputmode="text"]')).find((node) => {
	return isVisible(node) && !node.disabled && !node.readOnly && Number(node.maxLength || code.length || 6) > 1;
}) || null;

const otpBoxes = Array.from(document.querySelectorAll('input')).filter((node) => {
	if (!isVisible(node) || node.disabled || node.readOnly) {
		return false;
	}
	const maxLength = Number(node.maxLength || 0);
	const autocomplete = String(node.autocomplete || '').toLowerCase();
	return maxLength === 1 || autocomplete === 'one-time-code';
});

if (!input && otpBoxes.length < code.length) {
	return 'not-ready';
}

if (input) {
	input.focus();
	input.click();
	setNativeValue(input, code);
	dispatchInputEvents(input, code);

	const normalizedValue = String(input.value || '').trim();
	const expectedLength = Number(input.maxLength || code.length || 6);
	const slots = Array.from(document.querySelectorAll('[data-input-otp-slot="true"]'));
	const filledSlots = slots.filter((slot) => (slot.textContent || '').trim()).length;

	if (normalizedValue !== code) {
		return 'aggregate-mismatch';
	}

	if (expectedLength > 0 && normalizedValue.length !== expectedLength) {
		return 'aggregate-length-mismatch';
	}

	if (slots.length && filledSlots && filledSlots !== normalizedValue.length) {
		return 'aggregate-slot-mismatch';
	}

	input.blur();
	return 'filled';
}

const orderedBoxes = otpBoxes.slice(0, code.length);
for (let i = 0; i < orderedBoxes.length; i += 1) {
	const box = orderedBoxes[i];
	const char = code[i] || '';
	box.focus();
	box.click();
	setNativeValue(box, char);
	dispatchInputEvents(box, char);
	box.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: char }));
	box.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: char }));
	box.blur();
}

const merged = orderedBoxes.map((node) => String(node.value || '').trim()).join('');
return merged === code ? 'filled' : 'box-mismatch';
				""",
				code,
			)
		except PageDisconnectedError:
			refresh_active_page()
			if has_profile_form():
				logger.info("验证码提交后已跳转到最终注册页。")
				return code
			time.sleep(1)
			continue

		if filled == 'not-ready':
			if has_profile_form():
				logger.info("已直接进入最终注册页，跳过验证码按钮确认。")
				return code
			time.sleep(0.5)
			continue

		if filled != 'filled':
			logger.warning(f"验证码输入框已出现，但写入失败: {filled}")
			time.sleep(0.5)
			continue

		if filled == 'filled':
			time.sleep(1.2)
			try:
				clicked = browser.page.run_js(
					r"""
function isVisible(node) {
	if (!node) {
		return false;
	}
	const style = window.getComputedStyle(node);
	if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
		return false;
	}
	const rect = node.getBoundingClientRect();
	return rect.width > 0 && rect.height > 0;
}

const aggregateInput = Array.from(document.querySelectorAll('input[data-input-otp="true"], input[name="code"], input[autocomplete="one-time-code"], input[inputmode="numeric"], input[inputmode="text"]')).find((node) => {
	return isVisible(node) && !node.disabled && !node.readOnly && Number(node.maxLength || 0) > 1;
}) || null;

let value = '';
if (aggregateInput) {
	value = String(aggregateInput.value || '').trim();
	const expectedLength = Number(aggregateInput.maxLength || value.length || 6);
	if (!value || (expectedLength > 0 && value.length !== expectedLength)) {
		return false;
	}

	const slots = Array.from(document.querySelectorAll('[data-input-otp-slot="true"]'));
	if (slots.length) {
		const filledSlots = slots.filter((slot) => (slot.textContent || '').trim()).length;
		if (filledSlots && filledSlots !== value.length) {
			return false;
		}
	}
} else {
	const otpBoxes = Array.from(document.querySelectorAll('input')).filter((node) => {
		if (!isVisible(node) || node.disabled || node.readOnly) {
			return false;
		}
		const maxLength = Number(node.maxLength || 0);
		const autocomplete = String(node.autocomplete || '').toLowerCase();
		return maxLength === 1 || autocomplete === 'one-time-code';
	});
	value = otpBoxes.map((node) => String(node.value || '').trim()).join('');
	if (!value || value.length < 6) {
		return false;
	}
}

const buttons = Array.from(document.querySelectorAll('button[type="submit"], button')).filter((node) => {
	return isVisible(node) && !node.disabled && node.getAttribute('aria-disabled') !== 'true';
});
const confirmButton = buttons.find((node) => {
	const text = (node.innerText || node.textContent || '').replace(/\s+/g, '');
	const t = text.toLowerCase(); return text === '确认邮箱' || text.includes('确认邮箱') || text === '继续' || text.includes('继续') || text === '下一步' || text.includes('下一步') || t.includes('confirm') || t.includes('continue') || t.includes('next') || t.includes('verify');
});

if (!confirmButton) {
	return 'no-button';
}

confirmButton.focus();
confirmButton.click();
return 'clicked';
					"""
				)
			except PageDisconnectedError:
				refresh_active_page()
				if has_profile_form():
					logger.info("确认邮箱后页面跳转成功，已进入最终注册页。")
					return code
				clicked = 'disconnected'

			if clicked == 'clicked':
				logger.info(f"已填写验证码并点击确认邮箱: {code}")
				time.sleep(2)
				refresh_active_page()
				if has_profile_form():
					logger.info("验证码确认完成，最终注册页已就绪。")
					return code

			if clicked == 'no-button':
				current_url = browser.page.url
				if 'sign-up' in current_url or 'signup' in current_url:
					logger.info(f"已填写验证码，页面已自动跳转到下一步: {current_url}")
					return code

			if clicked == 'disconnected':
				time.sleep(1)
				continue

		time.sleep(0.5)

	debug_snapshot = browser.page.run_js(
		r"""
function isVisible(node) {
	if (!node) {
		return false;
	}
	const style = window.getComputedStyle(node);
	if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
		return false;
	}
	const rect = node.getBoundingClientRect();
	return rect.width > 0 && rect.height > 0;
}

const inputs = Array.from(document.querySelectorAll('input')).filter(isVisible).map((node) => ({
	type: node.type || '',
	name: node.name || '',
	testid: node.getAttribute('data-testid') || '',
	autocomplete: node.autocomplete || '',
	maxLength: Number(node.maxLength || 0),
	value: String(node.value || ''),
}));

const buttons = Array.from(document.querySelectorAll('button')).filter(isVisible).map((node) => ({
	text: String(node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim(),
	disabled: !!node.disabled,
	ariaDisabled: node.getAttribute('aria-disabled') || '',
}));

return { url: location.href, inputs, buttons };
		"""
	)
	logger.warning(f"验证码页 DOM 摘要: {debug_snapshot}")
	raise Exception("未找到验证码输入框或确认邮箱按钮")


def getTurnstileToken(total_timeout=90):
	"""获取 Turnstile token — CDP 点击 + 多种轮询 + 详细日志

	实际诊断结果: Turnstile iframe 不在 shadow DOM 中，直接作为 .cf-turnstile 的子元素。
	M3 的 shadow_root 方法不适用。改用 JS 直接定位 iframe 并 CDP dispatch 点击。
	"""
	# 不要 reset — 让 Turnstile 自然运行
	deadline = time.time() + total_timeout
	attempt = 0

	while time.time() < deadline:
		attempt += 1
		elapsed = int(time.time() - (deadline - total_timeout))

		# M1: turnstile.getResponse() API — 最直接
		try:
			turnstileResponse = browser.page.run_js("try { return turnstile.getResponse() } catch(e) { return null }")
			if turnstileResponse:
				logger.info(f"[Turnstile] M1-getResponse成功 (#{attempt}, {elapsed}s)")
				return turnstileResponse
		except Exception:
			pass

		# M2: 直接读 input 值
		try:
			direct_val = browser.page.run_js("""
const inp = document.querySelector('input[name="cf-turnstile-response"]');
return inp ? (inp.value || null) : null;
""")
			if direct_val:
				logger.info(f"[Turnstile] M2-input值成功 (#{attempt}, {elapsed}s)")
				return direct_val
		except Exception:
			pass

		# 诊断: 每10次或第3次
		if attempt == 3 or attempt % 10 == 0:
			try:
				_diag = browser.page.run_js("""
const inp = document.querySelector('input[name="cf-turnstile-response"]');
const cfDiv = document.querySelector('.cf-turnstile');
// 扩大搜索范围 — 检查多种可能的容器
const altContainers = document.querySelectorAll('[data-sitekey], [class*="turnstile"], [class*="cf-"], [id*="turnstile"], [id*="cf-"]');
let containerInfo = [];
altContainers.forEach(el => {
	containerInfo.push({
		tag: el.tagName,
		cls: (el.className || '').toString().substring(0, 50),
		id: (el.id || '').substring(0, 30),
		children: el.children.length,
		visible: el.offsetWidth > 0
	});
});
// 检查 Turnstile 脚本是否加载
const scripts = document.querySelectorAll('script[src*="turnstile"], script[src*="challenges.cloudflare"]');
let scriptInfo = [];
scripts.forEach(s => scriptInfo.push(s.src.substring(0, 80)));
const allIframes = document.querySelectorAll('iframe');
let turnstileIframes = [];
allIframes.forEach(ifr => {
	const src = ifr.src || '';
	if (src.includes('turnstile') || src.includes('challenges.cloudflare') || src.includes('captcha')) {
		turnstileIframes.push({ src: src.substring(0, 80), size: ifr.offsetWidth + 'x' + ifr.offsetHeight, visible: ifr.offsetWidth > 0 });
	}
});
// 查找 input 的父级结构
let parentInfo = '';
if (inp) {
	let p = inp.parentElement;
	const chain = [];
	while (p && chain.length < 5) {
		chain.push(p.tagName + (p.className ? '.' + p.className.toString().split(' ')[0] : '') + (p.id ? '#' + p.id : ''));
		p = p.parentElement;
	}
	parentInfo = chain.join(' > ');
}
// 检查 turnstile JS 全局变量
const hasTurnstileJS = typeof turnstile !== 'undefined';
const hasTurnstileObj = hasTurnstileJS ? Object.keys(turnstile).join(',') : 'none';
return {
	inputExists: !!inp,
	inputValue: inp ? (inp.value || '').substring(0, 20) : null,
	cfDivExists: !!cfDiv,
	parentChain: parentInfo,
	containersFound: containerInfo.slice(0, 5),
	turnstileIframes: turnstileIframes,
	scriptsLoaded: scriptInfo,
	totalIframes: allIframes.length,
	hasTurnstileJS: hasTurnstileJS,
	turnstileMethods: hasTurnstileObj
};
""")
				logger.info(f"[Turnstile] 诊断#{attempt} ({elapsed}s): input={_diag.get('inputExists')}, val={_diag.get('inputValue')}, cfDiv={_diag.get('cfDivExists')}, parent={_diag.get('parentChain')}, iframes={_diag.get('turnstileIframes')}, scripts={_diag.get('scriptsLoaded')}, turnstileJS={_diag.get('hasTurnstileJS')}({(_diag.get('turnstileMethods') or '')[:50]})")
			except Exception as e:
				logger.debug(f"[Turnstile] 诊断失败: {e}")

		# M3: JS 直接在 .cf-turnstile iframe 上 dispatch 真人化点击
		# 不用 DrissionPage 的 shadow_root API — iframe 不是在 shadow DOM 里
		if attempt % 3 == 1:
			try:
				click_result = browser.page.run_js("""
const cfDiv = document.querySelector('.cf-turnstile');
if (!cfDiv) return 'no-cf-div';
const ifr = cfDiv.querySelector('iframe');
if (!ifr) return 'no-iframe';

// 获取 iframe 位置用于坐标点击
const rect = ifr.getBoundingClientRect();
if (rect.width === 0 || rect.height === 0) return 'iframe-hidden:' + rect.width + 'x' + rect.height;

// 在 iframe 中心区域派发鼠标事件（模拟真人点击 checkbox 区域）
const centerX = rect.left + rect.width * 0.15;
const centerY = rect.top + rect.height * 0.5;

// 派发完整的鼠标事件链
['mousedown', 'mouseup', 'click'].forEach(type => {
	const evt = new MouseEvent(type, {
		bubbles: true, cancelable: true,
		view: window,
		screenX: centerX + Math.random() * 10,
		screenY: centerY + Math.random() * 10,
		clientX: centerX, clientY: centerY,
		button: 0
	});
	ifr.dispatchEvent(evt);
});

return 'clicked:' + Math.round(rect.width) + 'x' + Math.round(rect.height);
""")
				logger.debug(f"[Turnstile] M3-JS点击 (#{attempt}, {elapsed}s): {click_result}")
			except Exception as e:
				logger.debug(f"[Turnstile] M3-JS点击失败: {e}")

		# M4: 通过 CDP Input.dispatchMouseEvent 直接发送底层鼠标事件
		if attempt % 3 == 2:
			try:
				iframe_rect = browser.page.run_js("""
const cfDiv = document.querySelector('.cf-turnstile');
if (!cfDiv) return null;
const ifr = cfDiv.querySelector('iframe');
if (!ifr) return null;
const rect = ifr.getBoundingClientRect();
return { x: rect.left + rect.width * 0.15, y: rect.top + rect.height * 0.5, w: rect.width, h: rect.height };
""")
				if iframe_rect and iframe_rect.get('w', 0) > 0:
					x = float(iframe_rect['x'])
					y = float(iframe_rect['y'])
					browser.page.run_cdp("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
					time.sleep(0.1)
					browser.page.run_cdp("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
					time.sleep(0.05)
					browser.page.run_cdp("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)
					logger.debug(f"[Turnstile] M4-CDP点击 (#{attempt}, {elapsed}s)")
			except Exception as e:
				logger.debug(f"[Turnstile] M4-CDP点击失败: {e}")

		# M5: 每8次 reset turnstile widget
		if attempt % 8 == 0:
			try:
				browser.page.run_js("try { turnstile.reset(); } catch(e) {}")
				logger.info(f"[Turnstile] M5-reset (#{attempt}, {elapsed}s)")
			except Exception:
				pass

		# 等待 — 前期短后期长
		if attempt <= 15:
			time.sleep(1.5)
		elif attempt <= 30:
			time.sleep(2)
		else:
			time.sleep(3)

	logger.warning(f"[Turnstile] 超时 ({total_timeout}s, {attempt}次)")
	raise TimeoutError(f"Turnstile 解决超时（{total_timeout}s），未能获取 token")


def has_profile_form():
	refresh_active_page()
	try:
		return bool(browser.page.run_js(
			"""
const givenInput = document.querySelector('input[data-testid="givenName"], input[name="givenName"], input[autocomplete="given-name"]');
const familyInput = document.querySelector('input[data-testid="familyName"], input[name="familyName"], input[autocomplete="family-name"]');
const passwordInput = document.querySelector('input[data-testid="password"], input[name="password"], input[type="password"]');
return !!(givenInput && familyInput && passwordInput);
			"""
		))
	except Exception:
		return False


def build_profile():
	given_name = "Neo"
	family_name = "Lin"
	password = "N" + secrets.token_hex(4) + "!a7#" + secrets.token_urlsafe(6)
	return given_name, family_name, password


def fill_profile_and_submit(timeout=30):
	given_name, family_name, password = build_profile()
	deadline = time.time() + timeout
	turnstile_token = ""

	while time.time() < deadline:
		filled = browser.page.run_js(
			"""
const givenName = arguments[0];
const familyName = arguments[1];
const password = arguments[2];

function isVisible(node) {
	if (!node) {
		return false;
	}
	const style = window.getComputedStyle(node);
	if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
		return false;
	}
	const rect = node.getBoundingClientRect();
	return rect.width > 0 && rect.height > 0;
}

function pickInput(selector) {
	return Array.from(document.querySelectorAll(selector)).find((node) => {
		return isVisible(node) && !node.disabled && !node.readOnly;
	}) || null;
}

function setInputValue(input, value) {
	if (!input) {
		return false;
	}
	input.focus();
	input.click();

	const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
	const tracker = input._valueTracker;
	if (tracker) {
		tracker.setValue('');
	}

	if (nativeSetter) {
		nativeSetter.call(input, '');
		nativeSetter.call(input, value);
	} else {
		input.value = '';
		input.value = value;
	}

	input.dispatchEvent(new InputEvent('beforeinput', {
		bubbles: true,
		cancelable: true,
		data: value,
		inputType: 'insertText',
	}));
	input.dispatchEvent(new InputEvent('input', {
		bubbles: true,
		cancelable: true,
		data: value,
		inputType: 'insertText',
	}));
	input.dispatchEvent(new Event('change', { bubbles: true }));
	input.dispatchEvent(new Event('blur', { bubbles: true }));

	return String(input.value || '') === String(value || '');
}

const givenInput = pickInput('input[data-testid="givenName"], input[name="givenName"], input[autocomplete="given-name"]');
const familyInput = pickInput('input[data-testid="familyName"], input[name="familyName"], input[autocomplete="family-name"]');
const passwordInput = pickInput('input[data-testid="password"], input[name="password"], input[type="password"]');

if (!givenInput || !familyInput || !passwordInput) {
	return 'not-ready';
}

const givenOk = setInputValue(givenInput, givenName);
const familyOk = setInputValue(familyInput, familyName);
const passwordOk = setInputValue(passwordInput, password);

if (!givenOk || !familyOk || !passwordOk) {
	return 'filled-failed';
}

return [
	String(givenInput.value || '').trim() === String(givenName || '').trim(),
	String(familyInput.value || '').trim() === String(familyName || '').trim(),
	String(passwordInput.value || '') === String(password || ''),
].every(Boolean) ? 'filled' : 'verify-failed';
			""",
			given_name,
			family_name,
			password,
		)

		if filled == 'not-ready':
			time.sleep(0.5)
			continue

		if filled != 'filled':
			logger.warning(f"最终注册页输入框已出现，但姓名/密码写入失败: {filled}")
			time.sleep(0.5)
			continue

		values_ok = browser.page.run_js(
			"""
const expectedGiven = arguments[0];
const expectedFamily = arguments[1];
const expectedPassword = arguments[2];

function isVisible(node) {
	if (!node) {
		return false;
	}
	const style = window.getComputedStyle(node);
	if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
		return false;
	}
	const rect = node.getBoundingClientRect();
	return rect.width > 0 && rect.height > 0;
}

function pickInput(selector) {
	return Array.from(document.querySelectorAll(selector)).find((node) => {
		return isVisible(node) && !node.disabled && !node.readOnly;
	}) || null;
}

const givenInput = pickInput('input[data-testid="givenName"], input[name="givenName"], input[autocomplete="given-name"]');
const familyInput = pickInput('input[data-testid="familyName"], input[name="familyName"], input[autocomplete="family-name"]');
const passwordInput = pickInput('input[data-testid="password"], input[name="password"], input[type="password"]');

if (!givenInput || !familyInput || !passwordInput) {
	return false;
}

return String(givenInput.value || '').trim() === String(expectedGiven || '').trim()
	&& String(familyInput.value || '').trim() === String(expectedFamily || '').trim()
	&& String(passwordInput.value || '') === String(expectedPassword || '');
			""",
			given_name,
			family_name,
			password,
		)
		if not values_ok:
			logger.warning("最终注册页字段值校验失败，继续重试填写。")
			time.sleep(0.5)
			continue

		turnstile_state = browser.page.run_js(
			"""
const challengeInput = document.querySelector('input[name="cf-turnstile-response"]');
if (!challengeInput) {
	return 'not-found';
}
const value = String(challengeInput.value || '').trim();
return value ? 'ready' : 'pending';
			"""
		)

		if turnstile_state == "pending" and not turnstile_token:
			logger.info("检测到最终注册页存在 Turnstile，开始使用现有真人化点击逻辑。")
			turnstile_token = getTurnstileToken()
			if turnstile_token:
				synced = browser.page.run_js(
					"""
const token = arguments[0];
const challengeInput = document.querySelector('input[name="cf-turnstile-response"]');
if (!challengeInput) {
	return false;
}
const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
if (nativeSetter) {
	nativeSetter.call(challengeInput, token);
} else {
	challengeInput.value = token;
}
challengeInput.dispatchEvent(new Event('input', { bubbles: true }));
challengeInput.dispatchEvent(new Event('change', { bubbles: true }));
return String(challengeInput.value || '').trim() === String(token || '').trim();
					""",
					turnstile_token,
				)
				if synced:
					logger.info("Turnstile 响应已同步到最终注册表单。")

		time.sleep(1.2)

		try:
			submit_button = browser.page.ele('tag:button@@text()=完成注册') or browser.page.ele('tag:button@@text():Create Account') or browser.page.ele('tag:button@@text():Sign up')
		except Exception:
			submit_button = None

		if not submit_button:
			clicked = browser.page.run_js(
				r"""
const challengeInput = document.querySelector('input[name="cf-turnstile-response"]');
if (challengeInput && !String(challengeInput.value || '').trim()) {
	return false;
}
const buttons = Array.from(document.querySelectorAll('button[type="submit"], button'));
const submitButton = buttons.find((node) => {
	const text = (node.innerText || node.textContent || '').replace(/\s+/g, '');
	const t = text.toLowerCase(); return text === '完成注册' || text.includes('完成注册') || t.includes('create account') || t.includes('sign up') || t.includes('complete');
});
if (!submitButton || submitButton.disabled || submitButton.getAttribute('aria-disabled') === 'true') {
	return false;
}
submitButton.focus();
submitButton.click();
return true;
				"""
			)
		else:
			challenge_value = browser.page.run_js(
				"""
const challengeInput = document.querySelector('input[name="cf-turnstile-response"]');
return challengeInput ? String(challengeInput.value || '').trim() : 'not-found';
				"""
			)
			if challenge_value not in ('not-found', ''):
				submit_button.click()
				clicked = True
			else:
				clicked = False

		if clicked:
			logger.info(f"已填写注册资料并点击完成注册: {given_name} {family_name} / {password}")
			# 等待页面跳转或检查错误
			for _ in range(6):
				time.sleep(2)
				current_url = browser.page.url if browser.page else ""
				if 'sign-up' not in current_url:
					logger.info(f"注册页面已跳转到: {current_url}")
					break
				# 检查是否有错误消息
				error_msg = browser.page.run_js("""
const errs = document.querySelectorAll('[role="alert"], .error, [class*="error"], [class*="Error"]');
for (const e of errs) {
	const t = (e.innerText || e.textContent || '').trim();
	if (t) return t.substring(0, 100);
}
return '';
""")
				if error_msg:
					logger.warning(f"注册表单错误: {error_msg}")
			return {
				"given_name": given_name,
				"family_name": family_name,
				"password": password,
			}

		time.sleep(0.5)

	raise Exception("未找到最终注册表单或完成注册按钮")


def extract_visible_numbers(timeout=60):
	deadline = time.time() + timeout
	while time.time() < deadline:
		result = browser.page.run_js(
			r"""
function isVisible(el) {
	if (!el) {
		return false;
	}
	const style = window.getComputedStyle(el);
	if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
		return false;
	}
	const rect = el.getBoundingClientRect();
	return rect.width > 0 && rect.height > 0;
}

const selector = [
	'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
	'div', 'span', 'p', 'strong', 'b', 'small',
	'[data-testid]', '[class]', '[role="heading"]'
].join(',');

const seen = new Set();
const matches = [];
for (const node of document.querySelectorAll(selector)) {
	if (!isVisible(node)) {
		continue;
	}
	const text = String(node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
	if (!text) {
		continue;
	}
	const found = text.match(/\d+(?:\.\d+)?/g);
	if (!found) {
		continue;
	}
	for (const value of found) {
		const key = `${value}@@${text}`;
		if (seen.has(key)) {
			continue;
		}
		seen.add(key);
		matches.push({ value, text });
	}
}

return matches.slice(0, 30);
			"""
		)

		if result:
			logger.info("页面可见数字文本提取结果:")
			for item in result:
				try:
					logger.info(f" - 数字: {item['value']} | 上下文: {item['text']}")
				except Exception:
					pass
			return result

		time.sleep(1)

	raise Exception("登录后未提取到可见数字文本")


def run_single_registration(output_path=None, extract_numbers=False):
	"""单轮流程：打开注册页 -> 完成注册 -> 获取 sso -> 写 txt。"""
	from sso import wait_for_sso_cookie, append_sso_to_txt, DEFAULT_SSO_FILE
	if output_path is None:
		output_path = DEFAULT_SSO_FILE

	open_signup_page()
	email, dev_token = fill_email_and_submit()
	fill_code_and_submit(email, dev_token)
	profile = fill_profile_and_submit()
	sso_value = wait_for_sso_cookie()
	append_sso_to_txt(sso_value, output_path)

	if extract_numbers:
		try:
			refresh_active_page()
			extract_visible_numbers()
		except Exception as e:
			logger.warning(f"提取数字失败（page 可能已断开）: {e}")

	result = {
		"email": email,
		"sso": sso_value,
		**profile,
	}

	if run_logger:
		run_logger.info(
			"注册成功 | email=%s | password=%s | given=%s | family=%s",
			email,
			profile.get("password", ""),
			profile.get("given_name", ""),
			profile.get("family_name", ""),
		)

	logger.info(f"本轮注册完成，邮箱: {email}")
	return result
