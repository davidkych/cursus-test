<template>
  <div class="min-h-screen flex flex-col items-center justify-center">
    <h1 class="text-3xl font-bold mb-6">Sign in</h1>

    <button
      class="px-6 py-3 bg-blue-600 text-white rounded-xl shadow hover:bg-blue-700"
      @click="login"
    >
      Login with Microsoft
    </button>
  </div>
</template>

<script setup>
function login () {
  // After successful AAD sign-in SWA sends the user to /account/main
  window.location.href =
    '/.auth/login/aad?post_login_redirect_uri=/account/main';
}
</script>
