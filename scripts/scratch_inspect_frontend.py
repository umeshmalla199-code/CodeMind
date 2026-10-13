targets = [
    'function openAuthModal',
    'function switchAuthTab',
    'function handleRegisterSubmit',
    'function handleSignInSubmit',
    'function handleOtpSubmit',
    'function handleForgotPasswordSubmit',
    'function handleResetPasswordSubmit',
    'id="authRegisterForm"',
    'id="authOtpForm"',
    'id="authModal"',
    'function sendCompanionMessage',
    'function streamCompanionResponse'
]

with open('Frontend/index.html', encoding='utf-8') as f:
    for idx, line in enumerate(f, 1):
        for t in targets:
            if t in line:
                print(f'{t} at line {idx}')
