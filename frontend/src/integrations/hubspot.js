import { useState, useEffect } from 'react';
import { Box, Button, CircularProgress } from '@mui/material';
import axios from 'axios';

export const HubspotIntegration = ({ user, org, integrationParams, setIntegrationParams }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);

  const handleConnectClick = async () => {
    try {
      setIsConnecting(true);

      const formData = new FormData();
      formData.append('user_id', user);
      formData.append('org_id', org);

      const response = await axios.post(
        'http://localhost:8000/integrations/hubspot/authorize',
        formData
      );

      const authURL = response.data;
      const popup = window.open(authURL, 'HubSpot Auth', 'width=600,height=600');

      const timer = setInterval(() => {
        if (popup?.closed) {
          clearInterval(timer);
          handleWindowClosed();
        }
      }, 200);
    } catch (e) {
      setIsConnecting(false);
      alert(e?.response?.data?.detail);
    }
  };

  const handleWindowClosed = async () => {
    try {
      const formData = new FormData();
      formData.append('user_id', user);
      formData.append('org_id', org);

      const response = await axios.post(
        'http://localhost:8000/integrations/hubspot/credentials',
        formData
      );

      setIntegrationParams({
        credentials: response.data,
        type: 'HubSpot',
      });

      setIsConnected(true);
      setIsConnecting(false);
    } catch (e) {
      setIsConnecting(false);
      alert(e?.response?.data?.detail);
    }
  };

  useEffect(() => {
    setIsConnected(!!integrationParams?.credentials);
  }, []);

  return (
    <Box sx={{ mt: 2 }}>
      <Box display="flex" justifyContent="center">
        <Button
          variant="contained"
          color={isConnected ? 'success' : 'primary'}
          disabled={isConnecting || isConnected}
          onClick={handleConnectClick}
        >
          {isConnected ? 'HubSpot Connected' : isConnecting ? <CircularProgress size={20} /> : 'Connect to HubSpot'}
        </Button>
      </Box>
    </Box>
  );
};
