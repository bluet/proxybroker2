# Test Review Plan

## Objective
Audit all test changes made in the test-python13 branch to ensure:
1. Every line of test code is meaningful and necessary
2. No redundant or overfitted tests exist
3. Tests follow proper testing methodology
4. Code bugs and design issues are identified and documented

## Review Criteria

### Good Tests Should:
- **Test user-visible behavior**, not implementation details
- **Protect stable APIs** that users depend on
- **Enable refactoring** by not locking in internals
- **Be maintainable** and easy to understand
- **Actually test something** (not just mock everything)
- **Fail when functionality breaks**

### Bad Tests That Need Fixing:
- **Overfitting**: Testing exact internal state/calls
- **Meaningless**: Testing mocks instead of real behavior
- **Redundant**: Multiple tests for the same behavior
- **Brittle**: Fail on valid implementation changes
- **Incomplete**: Missing assert statements or error cases
- **Misleading**: Test name doesn't match what's tested

## Files to Review

### New Test Files (Added in this branch)
1. **test_api.py** (241 lines) - Rewritten to test Broker API behavior
2. **test_checker.py** (412 lines) - Tests proxy validation behavior
3. **test_cli.py** (466 lines) - Tests command-line interface
4. **test_integration.py** (272 lines) - Tests real usage patterns
5. **test_public_contracts.py** (430 lines) - Tests API stability
6. **test_server.py** (256 lines) - Tests proxy server behavior

### Modified Test Files
1. **test_negotiators.py** - Rewritten from byte sequences to behavior
2. **test_proxy.py** - Minor modifications
3. **test_resolver.py** - Minor modifications
4. **test_utils.py** - Minor modifications

### Supporting Files
1. **mock_server.py** (142 lines) - Mock HTTP server for tests
2. **utils.py** - Test utilities
3. **README.md** - Test documentation

## Review Process

### Phase 1: Test Quality Audit
For each test file:
1. Check if tests are behavior-focused vs implementation-focused
2. Identify redundant tests that test the same thing
3. Find incomplete tests (missing asserts, incomplete scenarios)
4. Spot overfitted tests that lock in implementation details
5. Verify test names match what they actually test

### Phase 2: Bug and Design Issue Discovery
While reviewing tests:
1. Document any bugs found in the actual code
2. Identify design issues or technical debt
3. Note areas where the API is confusing or inconsistent
4. Find missing error handling or edge cases

### Phase 3: Fix or Remove Bad Tests
1. Remove redundant tests
2. Rewrite overfitted tests to be behavior-focused
3. Complete incomplete tests
4. Fix misleading test names
5. Add missing critical tests

## Specific Areas of Concern

### Potential Issues to Check:
1. **Mock-heavy tests** - Are we testing real behavior or just mocks?
2. **Async handling** - Are async tests properly structured?
3. **Error scenarios** - Do we test failure modes adequately?
4. **Resource cleanup** - Are resources properly cleaned up in tests?
5. **Test isolation** - Do tests interfere with each other?

### Known Design Issues to Document:
1. Broker.serve() design issue (discovered earlier)
2. Event loop handling inconsistencies
3. Any other architectural issues found

## Expected Outcomes
1. Cleaner, more focused test suite
2. Documentation of bugs and design issues
3. Better test coverage of critical user paths
4. Removal of maintenance burden from bad tests
5. Clear understanding of what's stable vs flexible in the API