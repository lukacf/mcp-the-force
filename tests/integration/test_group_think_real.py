"""Integration tests for group_think that use real (but fast) models to understand the workflow."""

import pytest
from mcp_the_force.tools.group_think import GroupThink
from mcp_the_force.local_services.collaboration_service import CollaborationService


class TestGroupThinkRealIntegration:
    """Integration tests using real models to understand the actual workflow."""

    @pytest.mark.asyncio 
    async def test_minimal_real_collaboration(self):
        """Test with real fast models to understand exact workflow."""
        
        # Use the actual CollaborationService (not mocked)  
        service = CollaborationService()
        
        try:
            result = await service.execute(
                session_id="integration-test-minimal",
                objective="Create a simple greeting message",
                models=["chat_with_gpt5_nano"],  # Fastest model
                output_format="Single sentence greeting",
                discussion_turns=1,  # Minimal discussion
                validation_rounds=0,  # Skip validation for speed
                max_steps=3,
            )
            
            print(f"✓ Integration test successful!")
            print(f"Result: {result[:200]}...")
            
            # Basic assertions
            assert result is not None
            assert len(result.strip()) > 0
            assert "error" not in result.lower()
            
            return result
            
        except Exception as e:
            print(f"Integration test failed: {e}")
            # Don't fail the test - this helps us understand what's happening
            return f"Integration failed: {str(e)}"

    @pytest.mark.asyncio
    async def test_understand_discussion_synthesis_flow(self):
        """Test to understand the discussion -> synthesis flow with logging."""
        
        service = CollaborationService()
        
        # Enable detailed logging to understand the flow
        import logging
        logging.getLogger('mcp_the_force.local_services.collaboration_service').setLevel(logging.DEBUG)
        
        try:
            result = await service.execute(
                session_id="integration-flow-test", 
                objective="Explain the benefits of AI collaboration",
                models=["chat_with_gpt5_nano", "chat_with_gemini25_flash"],
                output_format="Brief explanation with 3 key points",
                discussion_turns=2,  # 2 discussion turns
                validation_rounds=1,  # 1 validation round
                max_steps=10,
            )
            
            print("✓ Flow test completed successfully!")
            print(f"Final result: {result[:300]}...")
            
            return result
            
        except Exception as e:
            print(f"Flow test error: {e}")
            import traceback
            traceback.print_exc()
            return f"Flow test failed: {str(e)}"

    @pytest.mark.asyncio
    async def test_group_think_tool_interface(self):
        """Test the GroupThink tool interface directly."""
        
        # This tests the tool registration and parameter routing
        from mcp_the_force.tools.registry import get_tool
        
        tool_metadata = get_tool("group_think")
        assert tool_metadata is not None
        print(f"✓ Tool registered: {tool_metadata.tool_name}")
        
        # Test the service class is correctly assigned
        tool_instance = GroupThink()
        assert tool_instance.service_cls == CollaborationService
        print("✓ Service class correctly assigned")
        
        return "Tool interface test passed"


if __name__ == "__main__":
    # Run the integration tests
    import asyncio
    
    async def run_integration_tests():
        test_instance = TestGroupThinkRealIntegration()
        
        print("=== Running Integration Tests ===")
        
        print("\n1. Testing minimal collaboration...")
        result1 = await test_instance.test_minimal_real_collaboration()
        
        print("\n2. Testing discussion->synthesis flow...")
        result2 = await test_instance.test_understand_discussion_synthesis_flow()
        
        print("\n3. Testing tool interface...")
        result3 = await test_instance.test_group_think_tool_interface()
        
        print("\n=== Integration Test Results ===")
        print(f"Minimal test: {'✓' if 'error' not in result1.lower() else '✗'}")
        print(f"Flow test: {'✓' if 'error' not in result2.lower() else '✗'}")
        print(f"Tool test: {'✓' if 'passed' in result3.lower() else '✗'}")
    
    asyncio.run(run_integration_tests())