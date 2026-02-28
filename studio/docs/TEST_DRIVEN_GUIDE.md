# Test-Driven Development Guide for Studio

This guide defines the test-driven discipline for technical implementations produced through Studio.

---

## Philosophy

**Every technical implementation should be testable and tested.** Tests are not an afterthought—they're part of the deliverable that proves the system works.

### What This Means

When you complete a tech phase run, you should have:
1. **Test specifications** — What behaviors will be tested
2. **Test code** — Executable tests that validate those behaviors
3. **Implementation code** — Code written to pass those tests
4. **Verification instructions** — How to run the tests and confirm everything works

---

## Test-Driven Workflow for Tech Phase

### Step 1: Define Testable Requirements (Advocate)

When advocating for a technical solution, specify:

**Functional Requirements:**
- What should the system do?
- What are the inputs and expected outputs?
- What are the edge cases?

**Non-Functional Requirements:**
- Performance targets (response time, throughput)
- Compatibility requirements (browsers, devices)
- Error handling expectations

**Example:**
```markdown
## Testable Requirements

### User Authentication
- **Requirement:** System validates user credentials
- **Input:** Username and password
- **Expected Output:** JWT token on success, error message on failure
- **Edge Cases:** Empty credentials, invalid format, expired tokens
- **Performance:** Response < 200ms for 95th percentile
```

### Step 2: Write Test Specifications (Implementation)

Before writing code, define what tests you'll write:

```markdown
## Test Specifications

### Unit Tests
1. `test_validate_credentials_success()` — Valid credentials return token
2. `test_validate_credentials_invalid()` — Invalid credentials return error
3. `test_validate_credentials_empty()` — Empty credentials return validation error
4. `test_token_generation()` — Generated tokens are valid JWT format
5. `test_token_expiration()` — Tokens expire after configured time

### Integration Tests
1. `test_auth_endpoint_success()` — POST /auth with valid creds returns 200
2. `test_auth_endpoint_failure()` — POST /auth with invalid creds returns 401
3. `test_auth_endpoint_rate_limit()` — Excessive requests are rate-limited

### Performance Tests
1. `test_auth_response_time()` — 95th percentile < 200ms under load
```

### Step 3: Write Tests First

Write the actual test code before implementation:

```javascript
// tests/auth.test.js

describe('Authentication', () => {
  test('validate_credentials_success', () => {
    const result = validateCredentials('user@example.com', 'password123');
    expect(result.success).toBe(true);
    expect(result.token).toBeDefined();
    expect(isValidJWT(result.token)).toBe(true);
  });

  test('validate_credentials_invalid', () => {
    const result = validateCredentials('user@example.com', 'wrongpassword');
    expect(result.success).toBe(false);
    expect(result.error).toBe('Invalid credentials');
  });

  test('validate_credentials_empty', () => {
    const result = validateCredentials('', '');
    expect(result.success).toBe(false);
    expect(result.error).toBe('Email and password required');
  });
});
```

**At this point, tests should fail** (because implementation doesn't exist yet).

### Step 4: Implement to Pass Tests

Write the minimum code needed to make tests pass:

```javascript
// src/auth.js

function validateCredentials(email, password) {
  // Validate inputs
  if (!email || !password) {
    return {
      success: false,
      error: 'Email and password required'
    };
  }

  // Check credentials (simplified example)
  const user = findUserByEmail(email);
  if (!user || !verifyPassword(password, user.passwordHash)) {
    return {
      success: false,
      error: 'Invalid credentials'
    };
  }

  // Generate token
  const token = generateJWT(user.id);
  return {
    success: true,
    token
  };
}
```

### Step 5: Verify Tests Pass

Run the tests and confirm they all pass:

```bash
npm test

# Expected output:
# ✓ validate_credentials_success (12ms)
# ✓ validate_credentials_invalid (8ms)
# ✓ validate_credentials_empty (5ms)
# 
# Tests: 3 passed, 3 total
```

### Step 6: Document Verification (Contrarian Review)

The contrarian should verify:
- ✅ Tests exist for all requirements
- ✅ Tests actually run and pass
- ✅ Edge cases are covered
- ✅ Performance requirements are tested
- ✅ Instructions to run tests are clear

---

## Test Types by Use Case

### Unit Tests
**When:** Testing individual functions or components in isolation
**Tools:** Jest, Mocha, pytest, unittest
**Example:**
```python
def test_calculate_damage():
    weapon = Weapon(damage=10, multiplier=1.5)
    result = calculate_damage(weapon, critical=True)
    assert result == 15
```

### Integration Tests
**When:** Testing how components work together
**Tools:** Supertest, Cypress, Playwright
**Example:**
```javascript
test('user can complete checkout flow', async () => {
  await addItemToCart('item-123');
  await proceedToCheckout();
  await enterPaymentInfo(testCard);
  const result = await submitOrder();
  expect(result.status).toBe('confirmed');
});
```

### End-to-End Tests
**When:** Testing complete user workflows
**Tools:** Playwright, Cypress, Selenium
**Example:**
```javascript
test('player can complete tutorial', async ({ page }) => {
  await page.goto('/game');
  await page.click('[data-testid="start-tutorial"]');
  await completeTutorialSteps(page);
  const achievement = await page.locator('.achievement-unlocked');
  expect(achievement).toContainText('Tutorial Complete');
});
```

### Performance Tests
**When:** Validating performance requirements
**Tools:** k6, Artillery, JMeter
**Example:**
```javascript
import http from 'k6/http';
import { check } from 'k6';

export let options = {
  vus: 100,
  duration: '30s',
};

export default function() {
  let res = http.get('https://api.example.com/data');
  check(res, {
    'response time < 200ms': (r) => r.timings.duration < 200,
  });
}
```

---

## Implementation.md Structure for Tech Phase

Your `implementation.md` should follow this structure:

```markdown
# [Feature Name] Implementation

## 1. Architecture Overview
[Diagram or description of components]

## 2. Technology Stack
- Language: JavaScript (Node.js 18+)
- Framework: Express.js
- Testing: Jest + Supertest
- Database: PostgreSQL

## 3. Test Specifications

### Unit Tests
- test_function_a()
- test_function_b()

### Integration Tests
- test_api_endpoint_x()
- test_api_endpoint_y()

## 4. Test Code

### tests/unit/feature.test.js
```javascript
// Full test code here
```

### tests/integration/api.test.js
```javascript
// Full test code here
```

## 5. Implementation Code

### src/feature.js
```javascript
// Full implementation here
```

## 6. Running Tests

```bash
# Install dependencies
npm install

# Run unit tests
npm run test:unit

# Run integration tests
npm run test:integration

# Run all tests
npm test
```

Expected output:
```
Tests: 15 passed, 15 total
Time: 2.3s
```

## 7. Verification Checklist

- [x] All tests pass
- [x] Code coverage > 80%
- [x] Edge cases tested
- [x] Performance requirements met
- [x] Error handling tested
- [x] Documentation complete
```

---

## Common Patterns

### Pattern 1: Test Data Fixtures

Create reusable test data:

```javascript
// tests/fixtures/users.js
export const validUser = {
  email: 'test@example.com',
  password: 'SecurePass123!',
  name: 'Test User'
};

export const invalidUser = {
  email: 'invalid-email',
  password: '123',
  name: ''
};
```

### Pattern 2: Test Helpers

Create helper functions for common test operations:

```javascript
// tests/helpers/auth.js
export async function loginAsUser(user) {
  const response = await request(app)
    .post('/auth/login')
    .send({ email: user.email, password: user.password });
  return response.body.token;
}
```

### Pattern 3: Mocking External Dependencies

Mock APIs, databases, etc.:

```javascript
// tests/unit/api.test.js
jest.mock('../src/database');
import { findUser } from '../src/database';

test('getUserById returns user', async () => {
  findUser.mockResolvedValue({ id: 1, name: 'Test' });
  const result = await getUserById(1);
  expect(result.name).toBe('Test');
});
```

---

## Quality Standards

### Minimum Requirements

Every tech implementation must have:
- ✅ At least 3 unit tests
- ✅ At least 1 integration test (if applicable)
- ✅ All tests passing
- ✅ Clear instructions to run tests
- ✅ Test coverage for happy path + error cases

### Good Test Characteristics

**Tests should be:**
- **Fast:** Run in milliseconds, not seconds
- **Isolated:** Don't depend on other tests
- **Repeatable:** Same result every time
- **Self-validating:** Pass or fail, no manual checking
- **Timely:** Written before or with implementation

**Tests should NOT be:**
- Flaky (sometimes pass, sometimes fail)
- Dependent on external services (use mocks)
- Testing implementation details (test behavior, not internals)
- Overly complex (tests should be simple to understand)

---

## Examples by Framework

### JavaScript/Node.js (Jest)

```javascript
// tests/calculator.test.js
const { add, subtract } = require('../src/calculator');

describe('Calculator', () => {
  test('adds two numbers', () => {
    expect(add(2, 3)).toBe(5);
  });

  test('subtracts two numbers', () => {
    expect(subtract(5, 3)).toBe(2);
  });
});
```

### Python (pytest)

```python
# tests/test_calculator.py
from src.calculator import add, subtract

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 3) == 2
```

### Web (Playwright)

```javascript
// tests/e2e/login.spec.js
import { test, expect } from '@playwright/test';

test('user can login', async ({ page }) => {
  await page.goto('/login');
  await page.fill('[name="email"]', 'test@example.com');
  await page.fill('[name="password"]', 'password123');
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL('/dashboard');
});
```

---

## Contrarian Review Checklist

When reviewing a tech implementation, verify:

### Test Coverage
- [ ] All functional requirements have tests
- [ ] Edge cases are tested
- [ ] Error handling is tested
- [ ] Performance requirements are tested (if applicable)

### Test Quality
- [ ] Tests are clear and well-named
- [ ] Tests are isolated (no dependencies between tests)
- [ ] Tests use appropriate assertions
- [ ] Tests don't test implementation details

### Implementation Quality
- [ ] Code passes all tests
- [ ] Code is readable and maintainable
- [ ] Error handling is implemented
- [ ] Performance is acceptable

### Documentation
- [ ] Instructions to run tests are clear
- [ ] Expected test output is documented
- [ ] Dependencies are listed
- [ ] Setup steps are documented

### Verification
- [ ] You actually ran the tests
- [ ] All tests passed
- [ ] No warnings or errors in test output
- [ ] Tests run in reasonable time (< 30s for unit tests)

---

## FAQ

### Q: Do I need 100% test coverage?

**A:** No. Aim for >80% coverage of critical paths. Focus on:
- Core business logic
- Edge cases and error handling
- Public APIs and interfaces
- Complex algorithms

Don't test:
- Trivial getters/setters
- Third-party library code
- Configuration files

### Q: Should I write tests for prototypes?

**A:** For quick prototypes, minimal tests are fine (1-2 smoke tests). For anything going to production or being shared, full test coverage is required.

### Q: What if the tech stack doesn't have good testing tools?

**A:** Choose a different tech stack. Testability is a requirement, not optional. If a framework/language doesn't have mature testing tools, it's not production-ready.

### Q: How do I test UI/visual elements?

**A:** Use visual regression testing (Percy, Chromatic) or component testing (Storybook + Playwright). At minimum, test that components render without errors and respond to interactions.

### Q: What about manual testing?

**A:** Manual testing is complementary, not a replacement. Automated tests catch regressions, manual testing validates UX and finds unexpected issues.

---

## Resources

### Testing Frameworks
- **JavaScript:** Jest, Vitest, Mocha
- **Python:** pytest, unittest
- **Web E2E:** Playwright, Cypress
- **Performance:** k6, Artillery

### Learning Resources
- [Test-Driven Development by Example](https://www.amazon.com/Test-Driven-Development-Kent-Beck/dp/0321146530) — Kent Beck
- [Jest Documentation](https://jestjs.io/docs/getting-started)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [pytest Documentation](https://docs.pytest.org/)

---

## Summary

**Test-driven development is not optional for tech implementations.** Every technical deliverable from Studio should include:

1. Test specifications
2. Test code
3. Implementation code
4. Verification instructions

This ensures that what we build is **provably correct**, **maintainable**, and **trustworthy**.
