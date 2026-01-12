"""
Tests for Form Handling (Step 2.6).

Tests cover:
- Form detection
- Form field extraction
- Read-only form detection
- GET form detection
"""

import asyncio

import pytest

from navigator.knowledge.exploration_engine import ExplorationEngine


class TestFormHandling:
	"""Tests for form handling (Step 2.6)."""

	async def test_discover_forms_from_page(self, exploration_engine, base_url, http_server):
		"""Test discovering forms from a webpage."""
		# Add a form page to the test server
		http_server.expect_request('/form').respond_with_data(
			'<html><head><title>Form Page</title></head><body>'
			'<h1>Contact Form</h1>'
			'<form action="/submit" method="GET">'
			'<input type="text" name="name" placeholder="Name">'
			'<input type="email" name="email" placeholder="Email">'
			'<textarea name="message" placeholder="Message"></textarea>'
			'<button type="submit">Submit</button>'
			'</form>'
			'</body></html>',
			content_type='text/html',
		)
		
		url = f"{base_url}/form"
		forms = await exploration_engine.discover_forms(url)
		
		assert len(forms) > 0
		form = forms[0]
		assert "action" in form
		assert "method" in form
		assert "fields" in form
		assert "attributes" in form
		assert form["method"] == "GET"
		assert form["action"] == f"{base_url}/submit"
		assert len(form["fields"]) > 0

	async def test_form_field_extraction(self, exploration_engine, base_url, http_server):
		"""Test that form fields are extracted correctly."""
		http_server.expect_request('/form_fields').respond_with_data(
			'<html><head><title>Form Fields</title></head><body>'
			'<form action="/submit" method="GET">'
			'<input type="text" name="name" id="name">'
			'<input type="email" name="email" id="email">'
			'<select name="country" id="country">'
			'<option value="us">US</option>'
			'</select>'
			'<textarea name="message" id="message"></textarea>'
			'</form>'
			'</body></html>',
			content_type='text/html',
		)
		
		url = f"{base_url}/form_fields"
		forms = await exploration_engine.discover_forms(url)
		
		assert len(forms) > 0
		form = forms[0]
		fields = form["fields"]
		
		# Check field types
		field_types = [f["type"] for f in fields]
		assert "input" in field_types
		assert "select" in field_types
		assert "textarea" in field_types
		
		# Check field attributes
		for field in fields:
			assert "type" in field
			assert "attributes" in field

	async def test_read_only_form_detection(self, exploration_engine):
		"""Test detection of read-only forms."""
		# Form with only hidden/readonly fields
		readonly_fields = [
			{"type": "input", "attributes": {"type": "hidden", "name": "token"}},
			{"type": "input", "attributes": {"type": "text", "name": "display", "readonly": ""}},
		]
		
		assert exploration_engine._is_read_only_form(readonly_fields) is True
		
		# Form with editable fields
		editable_fields = [
			{"type": "input", "attributes": {"type": "text", "name": "name"}},
			{"type": "input", "attributes": {"type": "email", "name": "email"}},
		]
		
		assert exploration_engine._is_read_only_form(editable_fields) is False

	async def test_get_form_detection(self, exploration_engine, base_url, http_server):
		"""Test that GET forms are detected and included."""
		http_server.expect_request('/get_form').respond_with_data(
			'<html><head><title>GET Form</title></head><body>'
			'<form action="/search" method="GET">'
			'<input type="text" name="q" placeholder="Search">'
			'<button type="submit">Search</button>'
			'</form>'
			'</body></html>',
			content_type='text/html',
		)
		
		url = f"{base_url}/get_form"
		forms = await exploration_engine.discover_forms(url)
		
		# GET forms should be included
		assert len(forms) > 0
		get_forms = [f for f in forms if f["method"] == "GET"]
		assert len(get_forms) > 0

	async def test_form_attributes_extraction(self, exploration_engine, base_url, http_server):
		"""Test that form attributes are extracted correctly."""
		http_server.expect_request('/form_attrs').respond_with_data(
			'<html><head><title>Form Attributes</title></head><body>'
			'<form action="/submit" method="POST" enctype="multipart/form-data" class="contact-form">'
			'<input type="text" name="name">'
			'</form>'
			'</body></html>',
			content_type='text/html',
		)
		
		url = f"{base_url}/form_attrs"
		forms = await exploration_engine.discover_forms(url)
		
		assert len(forms) > 0
		form = forms[0]
		assert "attributes" in form
		# Note: POST forms might be filtered out, but attributes should still be extracted
		# For this test, we're just verifying attribute extraction works
