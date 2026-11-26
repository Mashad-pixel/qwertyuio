# Frontend behaviour tests

These tests load the real pages and scripts from `frontend/` into jsdom, with a scripted API,
and check what staff and students see and which requests are sent.

    cd tests/frontend
    npm install
    npm test

They cover: the collection scanner, the kitchen board, staff sign-in, the admin overview and
orders, the admin pages that are not yet connected, demo-mode isolation, and the student
tracking and checkout guards.
